#!/usr/bin/env python3
"""Query any Hagstofa PX-Web table into labelled long-form JSON.

Generic CLI for downstream projects. Filters are a JSON object of dimension
codes to lists of value codes; omitted dimensions select all values. Output
preserves codes, labels and nulls. Raw responses are archived by content hash.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = 'https://px.hagstofa.is/pxis/api/v1/is/'

def unpack(data, metadata):
    ids = data['id']
    cats = [data['dimension'][key]['category'] for key in ids]
    codes = [sorted(c['index'], key=c['index'].get) if isinstance(c['index'], dict) else c['index'] for c in cats]
    labels = {v['code']:dict(zip(v['values'],v['valueTexts'])) for v in metadata['variables']}
    expected = 1
    for n in data['size']: expected *= n
    vals=data['value']
    if isinstance(vals,list) and len(vals)!=expected: raise ValueError('Unexpected value count')
    rows=[]
    for i, combo in enumerate(itertools.product(*codes)):
        row={k:v for k,v in zip(ids,combo)}
        row['labels']={k:labels[k][v] for k,v in zip(ids,combo)}
        row['value']=vals[i] if isinstance(vals,list) else vals.get(str(i))
        rows.append(row)
    return rows

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['list','fetch'])
    ap.add_argument('path', nargs='?', default='')
    ap.add_argument('--filters', default='{}')
    ap.add_argument('--since', default='2015')
    ap.add_argument('--out', type=Path)
    a=ap.parse_args()
    if '..' in a.path or a.path.startswith(('http','/')): raise ValueError('Expected relative PX path')
    with httpx.Client(timeout=60,headers={'User-Agent':'icelandic-data/1.0'},transport=httpx.HTTPTransport(retries=2)) as c:
        r=c.get(BASE+a.path);r.raise_for_status();meta=r.json()
        if a.command=='list': print(json.dumps(meta,ensure_ascii=False));return
        filters=json.loads(a.filters);q=[]
        for v in meta['variables']:
            values=filters.get(v['code'],v['values'])
            if v.get('time') or v['code'] in ['Mánuður','Ár','Ársfjórðungur']:
                if values and len(values[0])>=4: values=[x for x in values if x[:4]>=a.since]
            if not values or not set(values)<=set(v['values']):raise ValueError(f"Invalid selection: {v['code']}")
            q.append({'code':v['code'],'selection':{'filter':'item','values':values}})
        if set(filters)-{v['code'] for v in meta['variables']}:raise ValueError('Unknown filter dimension')
        r=c.post(BASE+a.path,json={'query':q,'response':{'format':'json-stat2'}});r.raise_for_status()
        sha=hashlib.sha256(r.content).hexdigest();raw=ROOT/'data/raw/hagstofan/query'/f'{sha}.json';raw.parent.mkdir(parents=True,exist_ok=True);raw.write_bytes(r.content)
        result={'source':BASE+a.path,'title':meta['title'],'raw_sha256':sha,'rows':unpack(r.json(),meta)}
        text=json.dumps(result,ensure_ascii=False,allow_nan=False)
        if a.out:
            a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(text,encoding='utf-8')
        else:print(text)
if __name__=='__main__':main()

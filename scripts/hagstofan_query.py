#!/usr/bin/env python3
"""Query any Hagstofa PX-Web table into labelled long-form JSON.

Generic CLI for downstream projects. Filters are a JSON object of dimension
codes to lists of value codes; omitted dimensions select all values. Output
preserves codes, labels and nulls, and carries the table's own documentation:
LAST-UPDATED (the real publication stamp), NOTE / VALUENOTE caveats in
Icelandic and English, units, reference period and methodology links.

Only the native ``px`` response format serialises those headers — json-stat2
returns ``note: null`` and an ``updated`` that is the table's creation date —
so ``fetch`` makes one json-stat2 request for the data and one ``px`` request
for the header. Raw responses are archived by content hash and every fetch is
appended to ``data/raw/hagstofan/query/index.jsonl`` keyed by table and
LAST-UPDATED, so a vintage can be named and revisions can be diffed.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import itertools
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = 'https://px.hagstofa.is/pxis/api/v1/is/'
RAW_DIR = ROOT / 'data' / 'raw' / 'hagstofan' / 'query'
TIME_CODES = ('Mánuður', 'Ár', 'Ársfjórðungur')

# KEY[lang](subkey)=value;  — value is one or more adjacent "quoted" strings
# (PX wraps long strings across lines) or a bare token. Strings never contain
# a double quote, so this cannot be fooled by a ';' inside a note.
_ENTRY = re.compile(
    r'^(?P<key>[A-Z][A-Z0-9-]*)(?:\[(?P<lang>[a-z]{2})\])?(?:\((?P<sub>.*?)\))?='
    r'(?P<val>(?:\s*"[^"]*")+|[^;]*);', re.M)
_TAG = re.compile(r'<[^>]+>')
# Hagstofan notes sometimes carry an unterminated anchor ("...pdf TARGET=_Time
# series ...") — the tag never closes, so drop it up to the TARGET token.
_DANGLING = re.compile(r'<a\s[^<>]*?target=_?(?:blank|self|top|parent)?', re.I)
_HREF = re.compile(r'href=["\']?([^"\' >]+)', re.I)


def decode_px(raw: bytes) -> str:
    """Decode a px body by its own CODEPAGE header, ignoring the HTTP charset
    (PX-Web says Windows-1252 while sending UTF-8 with a BOM)."""
    probe = raw[:2000].decode('latin-1')
    m = re.search(r'^CODEPAGE="([^"]+)"', probe, re.M)
    codepage = (m.group(1) if m else 'utf-8').lower()
    if codepage in ('utf-8', 'utf8'):
        return raw.decode('utf-8-sig')
    return raw.decode(codepage)


def _unquote(val: str) -> str:
    parts = re.findall(r'"([^"]*)"', val)
    return ''.join(parts) if parts else val.strip()


def _paragraphs(text: str) -> list[str]:
    """Split a PX note on '#' line breaks, strip HTML, unescape entities."""
    out = []
    for p in text.split('#'):
        p = ' '.join(html.unescape(_DANGLING.sub('', _TAG.sub('', p))).split())
        if p:
            out.append(p)
    return out


def parse_px_header(raw: bytes) -> dict:
    """Parse the header of a px response into table documentation.

    Returns last_updated (ISO), creation_date, units, refperiod, contents,
    notes {lang: [paragraphs]}, value_notes [{variable, value_label, lang,
    text}] and links (every href found in any note)."""
    text = decode_px(raw)
    header = text.split('\nDATA=', 1)[0]
    notes: dict[str, list[str]] = {}
    value_notes: list[dict] = []
    links: list[str] = []
    fields: dict[str, str] = {}
    for m in _ENTRY.finditer(header):
        key, lang, sub, val = m.group('key'), m.group('lang') or 'is', m.group('sub'), _unquote(m.group('val'))
        if key in ('NOTE', 'NOTEX'):
            links += _HREF.findall(val)
            notes.setdefault(lang, []).extend(_paragraphs(val))
        elif key in ('VALUENOTE', 'VALUENOTEX'):
            links += _HREF.findall(val)
            var, _, value_label = (sub or '').partition('","')
            value_notes.append({'variable': var.strip('"'), 'value_label': value_label.strip('"'),
                                'lang': lang, 'text': ' '.join(_paragraphs(val))})
        elif lang == 'is' and sub is None:
            fields[key] = val
    return {
        'last_updated': _px_stamp(fields.get('LAST-UPDATED')),
        'creation_date': _px_stamp(fields.get('CREATION-DATE')),
        'units': fields.get('UNITS'),
        'refperiod': fields.get('REFPERIOD'),
        'contents': fields.get('CONTENTS'),
        'notes': notes,
        'value_notes': value_notes,
        'links': list(dict.fromkeys(links)),
    }


def _px_stamp(s: str | None) -> str | None:
    """'20260219 09:00' -> '2026-02-19T09:00'."""
    if not s:
        return None
    try:
        return datetime.strptime(s, '%Y%m%d %H:%M').strftime('%Y-%m-%dT%H:%M')
    except ValueError:
        return s


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


def is_time(v: dict) -> bool:
    return bool(v.get('time')) or v['code'] in TIME_CODES


def build_query(meta, filters, since):
    q = []
    for v in meta['variables']:
        values = filters.get(v['code'], v['values'])
        if is_time(v) and values and len(values[0]) >= 4:
            values = [x for x in values if x[:4] >= since]
        if not values or not set(values) <= set(v['values']): raise ValueError(f"Invalid selection: {v['code']}")
        q.append({'code': v['code'], 'selection': {'filter': 'item', 'values': values}})
    if set(filters) - {v['code'] for v in meta['variables']}: raise ValueError('Unknown filter dimension')
    return q


def header_query(meta):
    """Cheapest selection that still returns every VALUENOTE: all values of
    the non-time dimensions, one period. PX-Web drops notes for unselected
    values."""
    return [{'code': v['code'], 'selection': {'filter': 'item',
             'values': v['values'][-1:] if is_time(v) else v['values']}} for v in meta['variables']]


def fetch_header(c, path, query):
    r = c.post(BASE + path, json={'query': query, 'response': {'format': 'px'}}); r.raise_for_status()
    return parse_px_header(r.content)


def record_fetch(path: str, filters: dict, since: str, last_updated: str | None, sha: str) -> None:
    """Append one vintage line to data/raw/hagstofan/query/index.jsonl.

    The vintage of a dataset is (path, last_updated); two lines for the same
    vintage with different raw_sha256 are a revision. Curated scripts call
    this too, so the index covers every Hagstofan fetch the repo makes."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    with (RAW_DIR / 'index.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps({'fetched_at': fetched_at, 'path': path, 'last_updated': last_updated,
                            'filters': filters, 'since': since, 'raw_sha256': sha}, ensure_ascii=False) + '\n')


def table_code(path: str) -> str:
    """'Efnahagur/.../VIS01300.px' -> 'VIS01300'."""
    return path.rsplit('/', 1)[-1].removesuffix('.px')


def document_table(c, path: str, query: list, sidecar: dict) -> dict | None:
    """Fetch the px header for one data selection and merge it into ``sidecar``
    (keyed by table code) for a curated script's ``.meta.json``.

    Never raises on an HTTP failure: the data pipeline must not depend on the
    notes, so the reason goes to stderr and the entry is simply absent. A
    repeat table (same code, another selection) merges value_notes and links
    instead of overwriting. Prints one stderr breadcrumb per table."""
    code = table_code(path)
    try:
        doc = fetch_header(c, path, query)
    except httpx.HTTPError as e:
        print(f"{code}: notes unavailable ({type(e).__name__}: {e})", file=sys.stderr)
        return None
    entry = sidecar.get(code)
    if entry is None:
        sidecar[code] = {'path': path, 'last_updated': doc['last_updated'],
                         'fetched_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                         'units': doc['units'], 'refperiod': doc['refperiod'], 'notes': doc['notes'],
                         'value_notes': list(doc['value_notes']), 'links': list(doc['links'])}
        print(f"{code}: last updated {doc['last_updated']}, {sum(map(len, doc['notes'].values()))} notes", file=sys.stderr)
    else:
        seen = {(v['variable'], v['value_label'], v['lang']) for v in entry['value_notes']}
        entry['value_notes'] += [v for v in doc['value_notes'] if (v['variable'], v['value_label'], v['lang']) not in seen]
        entry['links'] = list(dict.fromkeys(entry['links'] + doc['links']))
    return doc


def write_sidecar(file: Path, sidecar: dict, merge: bool = False) -> None:
    """Write a curated script's ``.meta.json``; ``merge`` keeps entries from a
    previous run for tables this run did not touch (partial fetches)."""
    out = {}
    if merge and file.exists():
        out = json.loads(file.read_text(encoding='utf-8'))
    out.update(sidecar)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')


def query_filters(query: list) -> dict:
    """The {dimension: [values]} form of a PX query, for record_fetch."""
    return {q['code']: q['selection']['values'] for q in query}


def breadcrumb(doc: dict) -> dict:
    """The short form of a table's documentation, for listings and stderr."""
    first = next((p for paras in doc['notes'].values() for p in paras), '')
    return {'last_updated': doc['last_updated'], 'notes_count': sum(map(len, doc['notes'].values())),
            'value_notes_count': len(doc['value_notes']),
            'note_preview': first[:160] + ('…' if len(first) > 160 else ''), 'links': doc['links']}


def list_catalogue(c, path, items):
    """Category listing, HATEOAS-style: every item carries the relative path to
    pass back to this CLI, tables carry last_updated, a note count and a
    preview so caveats are visible before anything is fetched."""
    from concurrent.futures import ThreadPoolExecutor
    prefix = path.rstrip('/') + '/' if path else ''
    def enrich(item):
        item = {**item, 'path': prefix + (item.get('id') or item['dbid'])}
        item['next'] = f"list {item['path']}"
        if item.get('type') != 't':
            return item
        try:
            r = c.get(BASE + item['path']); r.raise_for_status(); meta = r.json()
        except httpx.HTTPError as e:
            print(f"{item['path']}: metadata unavailable ({e})", file=sys.stderr); return item
        # one value per dimension: table-level NOTEs still come, VALUENOTEs do
        # not (PX-Web drops them for unselected values), so that count is omitted
        minimal = [{'code': v['code'], 'selection': {'filter': 'item', 'values': v['values'][-1:]}} for v in meta['variables']]
        try:
            crumb = breadcrumb(fetch_header(c, item['path'], minimal))
        except httpx.HTTPError as e:
            print(f"{item['path']}: notes unavailable ({e})", file=sys.stderr); return item
        return {**item, **{k: v for k, v in crumb.items() if k != 'value_notes_count'}}
    with ThreadPoolExecutor(8) as pool:
        return list(pool.map(enrich, items))


def describe_table(c, path, meta):
    """Table metadata with the full notes and a ready-to-run fetch hint."""
    doc = fetch_header(c, path, header_query(meta))
    example = {v['code']: v['values'][:1] for v in meta['variables'] if not is_time(v)}
    return {**meta, 'path': path, **doc,
            'next': f"fetch {path} --filters '{json.dumps(example, ensure_ascii=False)}' --since 2015",
            'notes_command': f"notes {path}"}


def render_notes(doc: dict, title: str) -> str:
    lines = [title, f"Last updated: {doc['last_updated']}   Units: {doc['units']}   Period: {doc['refperiod']}", '']
    for lang, paras in doc['notes'].items():
        lines.append(f'[{lang}]')
        lines += [f'  {p}' for p in paras]
        lines.append('')
    for vn in doc['value_notes']:
        lines.append(f"[{vn['lang']}] {vn['variable']} = {vn['value_label']}: {vn['text']}")
    if doc['links']:
        lines += ['', 'Links:'] + [f'  {u}' for u in doc['links']]
    return '\n'.join(lines).rstrip()


def main():
    ap=argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['list','fetch','notes'],
                    help='list: catalogue (with per-table breadcrumbs) or table metadata with full notes; '
                         'fetch: data + documentation; notes: readable caveats only')
    ap.add_argument('path', nargs='?', default='', help='relative PX path; a category, or a table ending in .px')
    ap.add_argument('--filters', default='{}', help='JSON {dimension-code: [value-codes]}')
    ap.add_argument('--since', default='2015', help='first year to keep on the time dimension')
    ap.add_argument('--out', type=Path)
    a=ap.parse_args()
    if '..' in a.path or a.path.startswith(('http','/')): raise ValueError('Expected relative PX path')
    is_table = a.path.endswith('.px')
    if a.command != 'list' and not is_table: raise ValueError(f'{a.command} needs a table path ending in .px')
    with httpx.Client(timeout=60,headers={'User-Agent':'icelandic-data/1.0'},transport=httpx.HTTPTransport(retries=2)) as c:
        r=c.get(BASE+a.path);r.raise_for_status();meta=r.json()
        if a.command=='list':
            out = describe_table(c, a.path, meta) if is_table else list_catalogue(c, a.path, meta)
            print(json.dumps(out,ensure_ascii=False));return
        if a.command=='notes':
            print(render_notes(fetch_header(c, a.path, header_query(meta)), meta['title']));return
        filters=json.loads(a.filters)
        q = build_query(meta, filters, a.since)
        fetched_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        r=c.post(BASE+a.path,json={'query':q,'response':{'format':'json-stat2'}});r.raise_for_status()
        doc = fetch_header(c, a.path, q)
        sha=hashlib.sha256(r.content).hexdigest();raw=RAW_DIR/f'{sha}.json';raw.parent.mkdir(parents=True,exist_ok=True);raw.write_bytes(r.content)
        record_fetch(a.path, filters, a.since, doc['last_updated'], sha)
        result={'source':BASE+a.path,'path':a.path,'title':meta['title'],**doc,'fetched_at':fetched_at,'raw_sha256':sha,'rows':unpack(r.json(),meta)}
        text=json.dumps(result,ensure_ascii=False,allow_nan=False)
        b = breadcrumb(doc)
        print(f"{a.path}: {len(result['rows'])} rows, last updated {b['last_updated']}, "
              f"{b['notes_count']} notes + {b['value_notes_count']} value notes — read them: notes {a.path}", file=sys.stderr)
        if a.out:
            a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(text,encoding='utf-8')
        else:print(text)
if __name__=='__main__':main()

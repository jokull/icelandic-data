#!/usr/bin/env python3
"""Download HMS public price/rent indices or purchase registry; no browser needed.

Raw responses are archived by hash. Output is UTF-8 CSV. Purchase registry
is ISO-8859-1 upstream; index files are UTF-8. No filtering is applied here.
"""
import argparse,hashlib
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parent.parent
BASE='https://frs3o1zldvgn.objectstorage.eu-frankfurt-1.oci.customer-oci.com/n/frs3o1zldvgn/b/public_data_for_download/o/'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('dataset',choices=['kaupvisitala','leiguvisitala','kaupskra']);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 r=httpx.get(BASE+a.dataset+'.csv',timeout=120,follow_redirects=True,headers={'User-Agent':'icelandic-data/1.0'});r.raise_for_status()
 raw=ROOT/'data/raw/hms/snapshots'/f'{hashlib.sha256(r.content).hexdigest()}.csv';raw.parent.mkdir(parents=True,exist_ok=True);raw.write_bytes(r.content)
 text=r.content.decode('iso-8859-1' if a.dataset=='kaupskra' else 'utf-8-sig')
 if '<html' in text[:500].lower():raise ValueError('Expected CSV, got HTML')
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(text,encoding='utf-8')
if __name__=='__main__':main()

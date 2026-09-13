from scripts.hagstofan_query import unpack, parse_px_header, decode_px, header_query, build_query

def test_sparse_json_stat_preserves_labels_and_nulls():
 meta={'variables':[{'code':'x','values':['a','b'],'valueTexts':['Þing','Önnur']} ]}
 data={'id':['x'],'size':[2],'dimension':{'x':{'category':{'index':{'b':1,'a':0}}}},'value':{'1':4}}
 assert unpack(data,meta)==[{'x':'a','labels':{'x':'Þing'},'value':None},{'x':'b','labels':{'x':'Önnur'},'value':4}]

# Shape mirrors a real PX-Web response: BOM, CODEPAGE header, a NOTE wrapped
# across lines mid-word, '#' paragraph breaks, an <A HREF> link, a semicolon
# inside a string, an [en] variant, and a VALUENOTE keyed by value label.
PX = ('﻿CHARSET="ANSI";\nAXIS-VERSION="2013";\nCODEPAGE="utf-8";\nLANGUAGE="is";\n'
      'TITLE="Atvinnuþátttaka 1991-2025";\nLAST-UPDATED="20260219 09:00";\nCREATION-DATE="20170201 13:34";\n'
      'UNITS="Fjöldi/hlutfall";\nREFPERIOD="1991-";\n'
      'NOTE="Tímaraðir voru uppfærðar; sjá <A HREF=https://x.is/g.pdf TARGET=_blank>Greinargerð</A>#Tímara"\n'
      '"ðir frá 2003.";\n'
      'NOTE[en]="Series were revised. See <A HREF=https://x.is/g.pdf TARGET=_Next paragraph.";\n'
      'VALUENOTE("Vísitala","Vísitala án húsnæðis")="Án leigu (041 og 042).";\n'
      'VALUENOTE("Liður","Breyting (%)")="Prósent.";\n'
      'DATA=\n1 2 3\n;\n').encode('utf-8')

def test_decode_px_uses_codepage_not_http_charset():
 assert decode_px(PX).startswith('CHARSET')
 latin=b'CHARSET="ANSI";\nCODEPAGE="iso-8859-1";\nNOTE="\xde\xf6";\nDATA=\n;'
 assert parse_px_header(latin)['notes']['is']==['Þö']

def test_parse_px_header():
 d=parse_px_header(PX)
 assert d['last_updated']=='2026-02-19T09:00'
 assert d['creation_date']=='2017-02-01T13:34'
 assert d['units']=='Fjöldi/hlutfall' and d['refperiod']=='1991-'
 assert d['notes']=={'is':['Tímaraðir voru uppfærðar; sjá Greinargerð','Tímaraðir frá 2003.'],'en':['Series were revised. See Next paragraph.']}
 assert d['value_notes']==[{'variable':'Vísitala','value_label':'Vísitala án húsnæðis','lang':'is','text':'Án leigu (041 og 042).'},
                           {'variable':'Liður','value_label':'Breyting (%)','lang':'is','text':'Prósent.'}]
 assert d['links']==['https://x.is/g.pdf']

META={'variables':[{'code':'Ár','values':['2014','2015','2016'],'valueTexts':['2014','2015','2016'],'time':True},
                   {'code':'Kyn','values':['0','1'],'valueTexts':['Alls','Karlar']}]}

def test_header_query_takes_all_values_one_period():
 assert header_query(META)==[{'code':'Ár','selection':{'filter':'item','values':['2016']}},
                             {'code':'Kyn','selection':{'filter':'item','values':['0','1']}}]

def test_build_query_applies_since_and_filters():
 q=build_query(META,{'Kyn':['1']},'2015')
 assert q[0]['selection']['values']==['2015','2016'] and q[1]['selection']['values']==['1']


import json
import httpx
from scripts import hagstofan_query as hq

def test_record_fetch_line_shape(tmp_path, monkeypatch):
 monkeypatch.setattr(hq,'RAW_DIR',tmp_path/'query')
 hq.record_fetch('a/b/X.px',{'Kyn':['0']},'2015','2026-02-19T09:00','abc')
 line=json.loads((tmp_path/'query'/'index.jsonl').read_text(encoding='utf-8'))
 assert set(line)=={'fetched_at','path','last_updated','filters','since','raw_sha256'}
 assert line['path']=='a/b/X.px' and line['filters']=={'Kyn':['0']} and line['since']=='2015' and line['raw_sha256']=='abc'

class _Client:
 def __init__(self,body=None,err=None): self.body,self.err,self.calls=body,err,0
 def post(self,url,json=None):
  self.calls+=1
  if self.err: raise self.err
  return httpx.Response(200,content=self.body,request=httpx.Request('POST',url))

def test_document_table_merges_repeat_and_survives_http_error(capsys):
 sidecar={}
 assert hq.document_table(_Client(PX),'x/VIS01300.px',[],sidecar)['last_updated']=='2026-02-19T09:00'
 assert sidecar['VIS01300']['path']=='x/VIS01300.px' and len(sidecar['VIS01300']['value_notes'])==2
 assert 'VIS01300: last updated 2026-02-19T09:00, 3 notes' in capsys.readouterr().err
 px2=PX.replace('VALUENOTE("Liður","Breyting (%)")="Prósent.";'.encode(),'VALUENOTE("Liður","Annad")="Nytt.";'.encode())
 hq.document_table(_Client(px2),'x/VIS01300.px',[],sidecar)   # repeat: merge, no overwrite
 assert [v['value_label'] for v in sidecar['VIS01300']['value_notes']]==['Vísitala án húsnæðis','Breyting (%)','Annad']
 err=httpx.ConnectTimeout('boom',request=httpx.Request('POST','http://x'))
 assert hq.document_table(_Client(err=err),'x/NEW.px',[],sidecar) is None
 assert 'NEW' not in sidecar and 'NEW: notes unavailable' in capsys.readouterr().err

def test_write_sidecar_merge(tmp_path):
 f=tmp_path/'o.meta.json'
 hq.write_sidecar(f,{'A':{'path':'a'},'B':{'path':'b'}})
 hq.write_sidecar(f,{'A':{'path':'a2'}},merge=True)
 assert json.loads(f.read_text(encoding='utf-8'))=={'A':{'path':'a2'},'B':{'path':'b'}}
 hq.write_sidecar(f,{'C':{'path':'c'}})
 assert json.loads(f.read_text(encoding='utf-8'))=={'C':{'path':'c'}}
 assert hq.query_filters(hq.header_query(META))=={'Ár':['2016'],'Kyn':['0','1']}

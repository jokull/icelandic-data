import argparse
import httpx
import pytest
from scripts import hms_indices as m


def test_failed_second_index_download_preserves_both_previous_files(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'RAW',tmp_path)
    for name in ['kaupvisitala.csv','leiguvisitala.csv']:(tmp_path/name).write_text('previous', encoding='utf-8')
    def get(url,**kwargs):
        body=b'AR,MANUDUR,VISITALA,VISITALA_HOFUDBORGARSVAEDI,VISITALA_LANDSBYGGD\n2026,7,100,101,99\n' if 'kaupvisitala' in url else b'<html>broken</html>'
        return httpx.Response(200,content=body,request=httpx.Request('GET',url))
    monkeypatch.setattr(httpx,'get',get)
    with pytest.raises(ValueError,match='schema'):m.cmd_fetch(argparse.Namespace())
    for name in ['kaupvisitala.csv','leiguvisitala.csv']:assert (tmp_path/name).read_text(encoding='utf-8')=='previous'


def test_published_col_blank_is_null():
    import polars as pl
    from datetime import date
    df = pl.DataFrame({"UTGAFUDAGUR": [" ", "2026-08-26"]}).with_columns(m.published_col())
    assert df["published"].to_list() == [None, date(2026, 8, 26)]

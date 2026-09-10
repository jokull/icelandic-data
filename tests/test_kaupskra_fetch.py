"""Offline tests for scripts/kaupskra_fetch.py.

The whole point of the fetch script is to turn the ISO-8859-1 export into a
usable UTF-8 copy, so the encoding conversion is what we guard here.
"""
from __future__ import annotations

from scripts.kaupskra_fetch import latin1_to_utf8


def test_latin1_to_utf8_decodes_icelandic_chars():
    # byte 0xe6 = æ, 0xf0 = ð, 0xf6 = ö — the characters that mojibake if the
    # Latin-1 export were read as UTF-8.
    raw = b"Sveitarf\xe9lagi\xf0 Skagastr\xf6nd"
    assert latin1_to_utf8(raw) == "Sveitarfélagið Skagaströnd"


def test_latin1_to_utf8_is_utf8_reencodable():
    text = latin1_to_utf8(b"Reykjav\xedkurborg")
    assert text == "Reykjavíkurborg"
    # Round-trips cleanly through a UTF-8 encode/decode, i.e. no lost bytes.
    assert text.encode("utf-8").decode("utf-8") == text


def test_invalid_download_preserves_previous_copy(tmp_path, monkeypatch):
    import argparse
    import httpx
    import pytest
    from contextlib import contextmanager
    from scripts import kaupskra_fetch as m
    monkeypatch.setattr(m,'RAW_DIR',tmp_path)
    monkeypatch.setattr(m,'DST',tmp_path/'kaupskra_utf8.csv')
    m.DST.write_text('previous valid data',encoding='utf-8')
    @contextmanager
    def response(*args,**kwargs):
        yield httpx.Response(200,content=b'<html>upstream error</html>',request=httpx.Request('GET',m.URL))
    monkeypatch.setattr(httpx,'stream',response)
    with pytest.raises(ValueError,match='schema'):m.cmd_fetch(argparse.Namespace())
    assert m.DST.read_text(encoding='utf-8')=='previous valid data'
    assert list(tmp_path.iterdir())==[m.DST]


def test_download_validates_and_retains_original_encoding(tmp_path, monkeypatch):
    import argparse
    import httpx
    from contextlib import contextmanager
    from scripts import kaupskra_fetch as m
    monkeypatch.setattr(m,'RAW_DIR',tmp_path);monkeypatch.setattr(m,'DST',tmp_path/'kaupskra_utf8.csv')
    raw='FAERSLUNUMER;THINGLYSTDAGS;UTGDAG;TEGUND\n1;2026-08-31 00:00:00.0;2026-08-01;Fjölbýli\n'.encode('latin1')
    @contextmanager
    def response(*args,**kwargs):
        yield httpx.Response(200,content=raw,request=httpx.Request('GET',m.URL))
    monkeypatch.setattr(httpx,'stream',response)
    assert m.cmd_fetch(argparse.Namespace())==0
    assert (tmp_path/'kaupskra.csv').read_bytes()==raw
    assert 'Fjölbýli' in m.DST.read_text(encoding='utf-8')
    assert m.inspect_csv(m.DST)==(1,'2026-08-31')

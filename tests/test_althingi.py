"""Offline regression tests for the Alþingi fetcher."""

from __future__ import annotations

import os
import types
import xml.etree.ElementTree as ET
from datetime import date, datetime

import polars as pl

from scripts import althingi


class _Response:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        pass


class _Client:
    def __init__(self, content: bytes):
        self.content = content
        self.calls = 0

    def get(self, *args, **kwargs) -> _Response:
        self.calls += 1
        return _Response(self.content)


def test_current_parliament_refreshes_an_expired_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(althingi, "RAW_DIR", tmp_path)
    monkeypatch.setattr(althingi, "REQUEST_DELAY", 0)

    cache = althingi._cache_path("loggjafarthing/yfirstandandi/", {})
    cache.write_bytes("<löggjafarþing><þing númer='156'/></löggjafarþing>".encode())
    os.utime(cache, (0, 0))

    client = _Client("<löggjafarþing><þing númer='157'/></löggjafarþing>".encode())
    assert althingi.current_thing(client) == 157
    assert client.calls == 1


def test_closed_parliament_cache_does_not_expire(tmp_path, monkeypatch):
    monkeypatch.setattr(althingi, "RAW_DIR", tmp_path)

    cache = althingi._cache_path("thingmalalisti/", {"lthing": 156})
    cache.write_bytes("<málaskrá/>".encode())
    os.utime(cache, (0, 0))

    client = _Client(b"<wrong/>")
    root = althingi.get_xml(client, "thingmalalisti/", {"lthing": 156})
    assert root.tag == "málaskrá"
    assert client.calls == 0


def test_list_is_unlimited_unless_limit_is_given(monkeypatch, capsys):
    rows = [
        {
            "thing": number,
            "timabil": "2025–2026",
            "thingsetning": "2025-09-09",
            "thinglok": None,
        }
        for number in range(1, 21)
    ]
    monkeypatch.setattr(althingi, "current_thing", lambda client, force=False: 20)
    monkeypatch.setattr(althingi, "parliaments", lambda client, force=False: pl.DataFrame(rows))

    args = types.SimpleNamespace(datasets=False, force=False, limit=None)
    althingi.cmd_list(args)
    assert capsys.readouterr().out.count(" -> ") == 20

    args.limit = 3
    althingi.cmd_list(args)
    assert capsys.readouterr().out.count(" -> ") == 3


def test_sitting_and_speech_timestamps_are_typed(monkeypatch):
    documents = {
        "thingfundir/": """
            <þingfundir><þingfundur númer="1">
              <fundarheiti>1. fundur</fundarheiti>
              <hefst><dagur>4.2.2025</dagur><dagurtími>2025-02-04T13:30:00</dagurtími></hefst>
              <fundursettur>2025-02-04T14:03:19</fundursettur>
              <fuslit>2025-02-04T14:30:56</fuslit>
            </þingfundur></þingfundir>
        """,
        "raedulisti/": """
            <ræðulisti><ræða>
              <ræðumaður id="1039"><nafn>Birgir Ármannsson</nafn></ræðumaður>
              <dagur>18.2.2025</dagur><fundur>7</fundur><fundarheiti>7. fundur</fundarheiti>
              <ræðahófst>2025-02-18T13:31:07</ræðahófst>
              <ræðulauk>2025-02-18T13:31:15</ræðulauk>
              <tegundræðu>ræða</tegundræðu><umræða>umræða</umræða>
              <mál><málsflokkur>A</málsflokkur><málsnúmer>1</málsnúmer><málsheiti>Mál</málsheiti></mál>
            </ræða></ræðulisti>
        """,
    }

    def fake_get_xml(client, path, params=None, force=False, max_age=None):
        return ET.fromstring(documents[path])

    monkeypatch.setattr(althingi, "get_xml", fake_get_xml)

    sitting = althingi.fetch_sittings(None, [156], False)["sittings"].row(0, named=True)
    speech = althingi.fetch_speeches(None, [156], False)["speeches"].row(0, named=True)

    assert isinstance(sitting["dagur"], date)
    assert isinstance(sitting["hefst"], datetime)
    assert isinstance(sitting["fundursettur"], datetime)
    assert isinstance(sitting["fundarslit"], datetime)
    assert isinstance(speech["dagur"], date)
    assert isinstance(speech["hofst"], datetime)
    assert isinstance(speech["lauk"], datetime)

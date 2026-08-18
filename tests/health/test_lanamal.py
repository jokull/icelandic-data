"""Health probe — Lánamál ríkisins (lanamal.is) government bond API."""

DETAIL_URL = "https://www.lanamal.is/api/market/LoadIndexedDetail"
HEADERS = {
    # Endpoint rejects bare curl with no headers; UA + Referer is enough.
    "User-Agent": "Mozilla/5.0 (compatible; icelandic-data-lanamal/1.0)",
    "Accept": "application/json",
    "Referer": "https://www.lanamal.is/markadsyfirlit/?type=bond&orderbookid=rikb_31_0124",
}


def test_bond_detail_serves_daily_fixings(http):
    """The LoadIndexedDetail contract scripts/lanamal.py reads: 200 + JSON
    array with a non-empty chartData daily-fixing series (UTF-16 JSON —
    httpx decodes from the BOM). One known, long-outstanding orderbook."""
    r = http.get(
        DETAIL_URL,
        params={"orderbookId": "RIKB_31_0124", "lang": "is"},
        headers=HEADERS,
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    payload = r.json()
    assert payload, f"empty payload from {r.request.url}"
    record = payload[0]
    assert "orderbookId" in record, f"unexpected shape: {sorted(record)}"
    chart = record.get("chartData", {}).get("chartData")
    assert chart, "chartData daily-fixing series is empty"
    assert isinstance(chart[-1][1], (int, float)), "chart point yield is not numeric"

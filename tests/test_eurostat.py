from scripts.eurostat import json_stat_to_long, dataset_meta

# Trimmed from a live nama_10_gdp?geo=DE&geo=FR&sinceTimePeriod=2024 response:
# DE 2024 = 4386940, DE 2025 = 4529710, FR 2024 = 2935236.2, FR 2025 = 2991055.9,
# all four flagged provisional. Last dimension (time) varies fastest.
JS = {
    "id": ["freq", "unit", "na_item", "geo", "time"],
    "size": [1, 1, 1, 2, 2],
    "updated": "2026-09-08T23:00:00+0200",
    "value": {"0": 4386940.0, "1": 4529710.0, "2": 2935236.2, "3": 2991055.9},
    "status": {"0": "p", "1": "p", "2": "p", "3": "p"},
    "dimension": {
        "freq": {"category": {"index": {"A": 0}, "label": {"A": "Annual"}}},
        "unit": {"category": {"index": {"CP_MEUR": 0}, "label": {"CP_MEUR": "Current prices, million euro"}}},
        "na_item": {"category": {"index": {"B1GQ": 0}, "label": {"B1GQ": "GDP"}}},
        "geo": {"category": {"index": {"DE": 0, "FR": 1}, "label": {"DE": "Germany", "FR": "France"}}},
        "time": {"category": {"index": {"2024": 0, "2025": 1}, "label": {"2024": "2024", "2025": "2025"}}},
    },
    "extension": {"id": "nama_10_gdp", "status": {"label": {"p": "provisional"}},
                  "annotation": [{"type": "ESMS_HTML", "href": "https://ec.europa.eu/eurostat/cache/metadata/en/nama_10_esms.htm"}]},
}


def test_last_dimension_varies_fastest():
    df = json_stat_to_long(JS)
    assert df.select("geo", "time", "value").rows() == [
        ("DE", "2024", 4386940.0), ("DE", "2025", 4529710.0),
        ("FR", "2024", 2935236.2), ("FR", "2025", 2991055.9),
    ]


def test_status_flags_and_labels_are_carried():
    df = json_stat_to_long(JS)
    assert df["status"].to_list() == ["p"] * 4 and df["status_label"].to_list() == ["provisional"] * 4
    unflagged = json_stat_to_long({**JS, "status": None, "extension": {}})
    assert unflagged["status"].to_list() == [""] * 4 and unflagged["status_label"].to_list() == [""] * 4


def test_dataset_meta_keeps_updated_and_legend():
    m = dataset_meta(JS, {"geo": "DE"})
    assert m["updated"] == "2026-09-08T23:00:00+0200" and m["flagged_cells"] == 4
    assert m["status_legend"] == {"p": "provisional"} and m["esms_html"].endswith("nama_10_esms.htm")

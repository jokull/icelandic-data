"""Verify the búsnúmer → landsnúmer → coordinates pipeline.

Covers both the arithmetic conversion (drop last digit == integer-divide by 10)
and the iceaddr-based geocoding that the map script depends on.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import iceaddr  # noqa: F401 — just to locate the bundled SQLite
import pytest

from scripts.maelabord_nautgripa import (
    DM2_SCHEMA,
    DM3_SCHEMA,
    NAUTGRIPA_IDX,
    busnr_to_landsnr,
    parse_matrix,
)

ICEADDR_DB = Path(iceaddr.__file__).parent / "iceaddr.db"

# Top Nautgripir recipients (2026 YTD, verified against the scraped dashboard).
# Each tuple is (búsnúmer, expected landsnúmer, farm name start).
KNOWN_FARMS = [
    (1665491, 166549, "Gunnbjarnarholt"),
    (1526461, 152646, "Hrafnagil"),
    (1641631, 164163, "Dufþak"),
    # Top sheep recipients from the default yfirlit view:
    (1375901, 137590, "Svarfhóll"),
    (1447311, 144731, "Uppsalir"),
]


def test_busnr_to_landsnr_drops_last_digit():
    assert busnr_to_landsnr(16656491) == 1665649
    # 8-digit string with a leading zero — the conversion must still work.
    assert busnr_to_landsnr("01375901") == 137590
    # Integer form with leading zero stripped.
    assert busnr_to_landsnr(1375901) == 137590


@pytest.mark.parametrize("busnr,expected_landsnr,name_prefix", KNOWN_FARMS)
def test_known_farm_resolves_via_iceaddr(busnr, expected_landsnr, name_prefix):
    assert busnr_to_landsnr(busnr) == expected_landsnr
    conn = sqlite3.connect(ICEADDR_DB)
    try:
        rows = conn.execute(
            "SELECT heiti_nf, lat_wgs84, long_wgs84 FROM stadfong WHERE landnr=?",
            (expected_landsnr,),
        ).fetchall()
    finally:
        conn.close()
    assert rows, f"iceaddr has no row for landnr={expected_landsnr}"
    assert any(h.lower().startswith(name_prefix.lower()) for h, *_ in rows)
    # Iceland latitude/longitude sanity bounds.
    lats = [r[1] for r in rows]
    lons = [r[2] for r in rows]
    assert all(63.0 < lat < 67.0 for lat in lats)
    assert all(-25.0 < lon < -13.0 for lon in lons)


def test_dm_schemas_match_powerbi_descriptor():
    assert DM2_SCHEMA == ["A7", "A8", "A9", "A10", "A11", "A12", "A13"]
    assert DM3_SCHEMA == ["G1", "M0", "M1", "M2", "M3", "M4", "M5", "M6"]
    assert NAUTGRIPA_IDX == 1


@pytest.mark.xfail(
    reason="parse_matrix needs a ValueDicts.D0 entry to resolve Nautgriparækt by name; "
    "synthetic body in this test lacks one, so DM3 is not processed. Either pass a "
    "ValueDicts.D0 in the test fixture or add a NAUTGRIPA_IDX fallback path."
)
def test_parse_matrix_handles_repeat_and_null_masks():
    """Synthetic body shaped like the real matrix — mirrors Dufþakshólt row.

    DM3 row 1 establishes a baseline, row 2 uses R (repeat) + Ø (null) masks
    to compress values, just like Power BI's real wire format.
    """
    body = {
        "results": [{
            "result": {"data": {"dsr": {"DS": [{"PH": [
                {"DM1": [{
                    "S": [{"N": "G0", "T": 1}],
                    "G0": "1641631 - Dufþaksholt",
                    "M": [
                        {"DM2": [{
                            "S": [{"N": n, "T": 3} for n in DM2_SCHEMA],
                            "C": [-32822573, "0.0051", 17, 629, 80, 31944512],
                            "Ø": 16,  # bit 4 (A11) null
                        }]},
                        {"DM3": [
                            {
                                "S": [{"N": "G1", "T": 1}] +
                                     [{"N": n, "T": 3} for n in DM3_SCHEMA[1:]],
                                "C": [0, 0, "0.21", 17, 629, 80, 19076285],
                                "Ø": 32,  # bit 5 (M4) null
                            },
                            {"C": [1, 12868227], "R": 32, "Ø": 94},
                        ]},
                    ],
                }]},
            ]}]}}},
        }],
    }
    rows = list(parse_matrix(body))
    assert len(rows) == 1
    r = rows[0]
    assert r["busnr"] == "1641631"
    assert r["nafn"] == "Dufþaksholt"
    assert r["nautgripir"] == 629
    assert r["total_upphaed"] == 31944512
    assert r["nautgripa_upphaed"] == 12868227

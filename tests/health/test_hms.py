"""Health probe — HMS (Húsnæðis- og mannvirkjastofnun) bulk downloads.

Contract: the two bulk files this repo pulls from HMS are still reachable, still
the format we parse, and still being refreshed.

  - **Kaupskrá fasteigna** — the property-transaction CSV behind
    `data/processed/kaupskra_geocoded.parquet`. Semicolon-delimited, ISO-8859-1.
  - **Landeignaskrá** — the land-parcel shapefile ZIP that
    `scripts/landeignaskra.py` downloads (`BLOB_URL`) and builds landsnr →
    lon/lat from.

Neither is fetched. Kaupskrá is ~48 MB and Landeignaskrá ~25 MB, so this probe
uses HEAD for reachability plus a **Range request for the first few hundred
bytes** — enough to assert magic bytes on the ZIP and the full column header on
the CSV, which is where a schema change would actually show up. Downloading
either belongs in a fetch run, not a daily health check.

Two things deliberately *not* probed:

  - `hms.is` itself (the Landeignaskrá landing page, `LANDING_URL`) is behind a
    Vercel anti-bot checkpoint and returns the challenge HTML to httpx, so a
    probe of it would report a permanent false failure. It is only needed for
    `landeignaskra.py discover`, which is a Playwright path. The Azure blob it
    points at is world-readable and is the URL the code actually uses.
  - `scripts/hms_indices.py` has no upstream to probe: kaup-/leiguvísitala are
    manual downloads from the (Vercel-guarded) hms.is dashboard, and the script
    only reads `data/raw/hms/indices/*.csv` off disk.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import pytest

from scripts.landeignaskra import BLOB_URL
from tests.health.conftest import assert_fresh

# Kaupskrá's URL lives only in the hms skill — no script constant to import,
# since the download predates scripts/ and is done ad hoc. See
# .agents/skills/hms/SKILL.md § "Kaupskrá fasteigna".
KAUPSKRA_URL = (
    "https://frs3o1zldvgn.objectstorage.eu-frankfurt-1.oci.customer-oci.com"
    "/n/frs3o1zldvgn/b/public_data_for_download/o/kaupskra.csv"
)

# Every column the skill's field table documents. Asserting the set (not the
# order, and not that it is exhaustive) catches a rename or a dropped column
# while tolerating HMS appending new ones.
KAUPSKRA_COLUMNS = {
    "FAERSLUNUMER",
    "FASTNUM",
    "HEIMILISFANG",
    "POSTNR",
    "HEINUM",
    "SVFN",
    "SVEITARFELAG",
    "UTGDAG",
    "THINGLYSTDAGS",
    "KAUPVERD",
    "FASTEIGNAMAT",
    "FASTEIGNAMAT_GILDANDI",
    "BRUNABOTAMAT_GILDANDI",
    "BYGGAR",
    "EINFLM",
    "LOD_FLM",
    "FJHERB",
    "TEGUND",
    "FULLBUID",
    "ONOTHAEFUR_SAMNINGUR",
}


def _last_modified(response) -> datetime:
    raw = response.headers.get("last-modified")
    assert raw, f"{response.request.url} -> no Last-Modified header"
    return parsedate_to_datetime(raw)


# ── Landeignaskrá ────────────────────────────────────────────────────────


def test_landeignaskra_blob_is_reachable(http):
    """HEAD only — 25 MB of shapefile is not a health check."""
    r = http.head(BLOB_URL)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    ctype = r.headers.get("content-type", "")
    assert "zip" in ctype.lower(), f"{BLOB_URL} -> content-type {ctype!r}, expected a ZIP"

    size = int(r.headers.get("content-length", 0))
    # Plausibility, not an exact size — the registry grows as parcels are added.
    assert size > 5_000_000, (
        f"{BLOB_URL} -> Content-Length {size:,} bytes; the 89k-parcel shapefile "
        f"should be tens of MB — truncated or replaced?"
    )


def test_landeignaskra_blob_is_a_zip(http):
    """Range request for 4 bytes — proves it is really a ZIP, not an error page.

    Azure will happily serve an XML error body with a 200 in some misconfigured
    states; the magic bytes are what `zipfile.ZipFile` in `cmd_extract()` needs.
    """
    r = http.get(BLOB_URL, headers={"Range": "bytes=0-3"})
    assert r.status_code in (200, 206), f"{r.request.url} -> {r.status_code}"
    assert r.content[:2] == b"PK", (
        f"{BLOB_URL} does not start with ZIP magic; got {r.content[:8]!r}"
    )


@pytest.mark.degraded_ok
def test_landeignaskra_blob_is_fresh(http):
    r = http.head(BLOB_URL)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    # HMS refreshes the blob roughly daily; 30 days is loose enough that only a
    # genuinely abandoned export trips it.
    assert_fresh(_last_modified(r), timedelta(days=30), label="Landeignaskrá ZIP")


# ── Kaupskrá ─────────────────────────────────────────────────────────────


def test_kaupskra_is_reachable(http):
    """HEAD only — the CSV is ~48 MB."""
    r = http.head(KAUPSKRA_URL)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"

    size = int(r.headers.get("content-length", 0))
    assert size > 10_000_000, (
        f"{KAUPSKRA_URL} -> Content-Length {size:,} bytes; ~222k transactions "
        f"should be tens of MB — truncated?"
    )


def test_kaupskra_header_row_is_intact(http):
    """Range request for the first 400 bytes — the whole contract in one line.

    Covers the three things every kaupskrá query assumes: the semicolon
    delimiter, ISO-8859-1 decodability, and the column names.
    """
    r = http.get(KAUPSKRA_URL, headers={"Range": "bytes=0-399"})
    assert r.status_code in (200, 206), f"{r.request.url} -> {r.status_code}"

    text = r.content.decode("iso-8859-1")
    header = text.splitlines()[0]
    assert ";" in header, (
        f"kaupskra.csv header has no ';' — delimiter changed? got {header[:120]!r}"
    )

    columns = {field.strip().upper() for field in header.split(";")}
    missing = KAUPSKRA_COLUMNS - columns
    assert not missing, (
        f"{KAUPSKRA_URL} -> {r.status_code}: kaupskra.csv is missing documented "
        f"columns {sorted(missing)}; header={header[:200]!r}"
    )


@pytest.mark.degraded_ok
def test_kaupskra_is_fresh(http):
    """Kaupskrá is advertised as a daily export."""
    r = http.head(KAUPSKRA_URL)
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}"
    assert_fresh(_last_modified(r), timedelta(days=7), label="Kaupskrá CSV")

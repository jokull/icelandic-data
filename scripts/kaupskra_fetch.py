"""Fetch HMS kaupskrá (property-transaction registry) and convert to UTF-8.

The raw export at the direct object-storage URL is semicolon-delimited and
**ISO-8859-1** encoded — municipality names show up as mojibake unless the
bytes are decoded as Latin-1 first (verified: byte 0xe6/0xf0/0xf6 in
'Sveitarfélagið Skagaströnd'). The hms.is HTML page about the registry is
behind a Vercel checkpoint, but the blob it links is world-readable, so we
fetch it directly with httpx.

This script downloads the ~48 MB CSV once and writes a UTF-8 copy to
``data/raw/hms/kaupskra_utf8.csv`` — the file that downstream housing
analysis reads (see ``data/processed/kaupskra_geocoded.parquet`` and the
``iceaddr`` geocoding flow). It then reports the row count and the newest
``THINGLYSTDAGS`` so a stale local copy is obvious.

Usage:
    uv run python scripts/kaupskra_fetch.py            # fetch, convert, report freshness
    uv run python scripts/kaupskra_fetch.py report     # re-report an existing copy
"""
from __future__ import annotations

import argparse
import sys
from tempfile import TemporaryDirectory
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "hms"
DST = RAW_DIR / "kaupskra_utf8.csv"

URL = (
    "https://frs3o1zldvgn.objectstorage.eu-frankfurt-1.oci.customer-oci.com"
    "/n/frs3o1zldvgn/b/public_data_for_download/o/kaupskra.csv"
)

# The original Latin-1 export is retained alongside the UTF-8 copy. Decoding Latin-1 is byte-per-codepoint (0x00-0xFF -> U+0000-U+00FF),
# so every chunk boundary is safe to decode independently.
HEADERS = {"User-Agent": "icelandic-data/1.0 (data toolkit fetcher)"}


def latin1_to_utf8(raw: bytes) -> str:
    """Decode a Latin-1 bytes chunk to a Python str (then written as UTF-8).

    Latin-1 is byte-per-codepoint, so any chunk boundary is safe to decode
    independently. This is the step that prevents municipality-name mojibake.
    """
    return raw.decode("iso-8859-1")


def cmd_fetch(args: argparse.Namespace) -> int:
    import httpx

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Stage both encodings and validate before replacing a last-good download.
    with TemporaryDirectory(dir=RAW_DIR, prefix="kaupskra-") as staging:
        raw_path = Path(staging) / "kaupskra.csv"
        utf8_path = Path(staging) / "kaupskra_utf8.csv"
        with httpx.stream("GET", URL, follow_redirects=True, timeout=300.0, headers=HEADERS) as r:
            r.raise_for_status()
            with raw_path.open("wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
            last_modified = r.headers.get("last-modified", "(unknown)")
        convert_and_validate(raw_path, utf8_path)
        raw_path.replace(RAW_DIR / "kaupskra.csv")
        utf8_path.replace(DST)
    print(f"  saved: {DST}; source last-modified: {last_modified}", file=sys.stderr)
    return report(args)


def inspect_csv(path: Path) -> tuple[int, str]:
    import polars as pl
    df = pl.read_csv(path, separator=";", infer_schema_length=0)
    required = {"FAERSLUNUMER", "THINGLYSTDAGS", "UTGDAG", "TEGUND"}
    if not required <= set(df.columns) or not df.height:
        raise ValueError("Empty or unexpected kaupskrá schema")
    dates = df["THINGLYSTDAGS"].drop_nulls().filter(df["THINGLYSTDAGS"].drop_nulls().str.strip_chars() != "")
    if not len(dates):
        raise ValueError("No registration dates in kaupskrá")
    parsed = dates.str.slice(0,10).str.to_date("%Y-%m-%d", strict=True)
    return df.height, str(parsed.max())


def convert_and_validate(raw_path: Path, utf8_path: Path) -> None:
    with raw_path.open("rb") as raw, utf8_path.open("w", encoding="utf-8", newline="") as out:
        while chunk := raw.read(1 << 16):
            out.write(latin1_to_utf8(chunk))
    inspect_csv(utf8_path)


def cmd_report(args: argparse.Namespace) -> int:
    """Print freshness for the existing UTF-8 copy (no download)."""
    if not DST.exists():
        print(f"ERROR: {DST} not found — run `fetch` first", file=sys.stderr)
        return 1
    return report(args)


def report(args: argparse.Namespace) -> int:
    n, newest = inspect_csv(DST)
    print(f"\n{kaupskra_summary(n, newest)}")
    return 0


def kaupskra_summary(n: int, newest: str | None) -> str:
    return f"kaupskra_utf8.csv: {n:,} rows, newest THINGLYSTDAGS = {newest or '(none)'}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    f = sub.add_parser("fetch", help="download kaupskra.csv, convert to UTF-8, report freshness")
    f.set_defaults(func=cmd_fetch)
    r = sub.add_parser("report", help="report freshness of the existing UTF-8 copy")
    r.set_defaults(func=cmd_report)
    # Bare run == fetch (AGENTS.md quick command)
    ap.set_defaults(func=cmd_fetch)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

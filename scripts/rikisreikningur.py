"""Ríkisreikningur — state accounts (Fjársýsla ríkisins).

rikisreikningur.is is a React SPA backed by a small Azure Functions API at
`rikisreikningurapi.azurewebsites.net`. The API publishes government-wide
revenue/expense series, sub-totals by policy area (málefnasvið), and a file
manifest of published XLSX/PDF reports.

The API requires a static X-Api-Key header. The key is embedded in the public
JS bundle (it is effectively an anonymous throttling key, not a secret).

Usage:
    uv run python scripts/rikisreikningur.py timabil          # Current period
    uv run python scripts/rikisreikningur.py summary          # Yearly surplus + revenue/expense
    uv run python scripts/rikisreikningur.py malefni          # Policy-area breakdown CSV
    uv run python scripts/rikisreikningur.py files            # List published files
    uv run python scripts/rikisreikningur.py download --name <file>
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.parse
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

API_BASE = "https://rikisreikningurapi.azurewebsites.net"
# Static public API key, extracted from the SPA's main JS bundle. Not a
# secret — re-read from the bundle if the API starts returning 401.
API_KEY = "6d4d7394-2992-473d-9ea7-45946b39ad9d"

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "rikisreikningur"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"X-Api-Key": API_KEY, "accept": "text/plain"},
        timeout=60,
        follow_redirects=True,
    )


def _decode_data(payload):
    """The /api/FJS/Data/* endpoints return [str] where the string is itself
    JSON. Unwrap both layers so callers get the intended object."""
    if isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], str):
        return json.loads(payload[0])
    return payload


def fetch_timabil(client: httpx.Client) -> dict:
    r = client.get(f"{API_BASE}/api/FJS/NuverandiTimabil")
    r.raise_for_status()
    return r.json()


def fetch_tekjur_og_gjold(client: httpx.Client) -> dict:
    r = client.get(f"{API_BASE}/api/FJS/TekjurOgGjold")
    r.raise_for_status()
    return r.json()


def fetch_malefni(client: httpx.Client) -> list[dict]:
    r = client.get(f"{API_BASE}/api/FJS/Data/malefni_tg")
    r.raise_for_status()
    decoded = _decode_data(r.json())
    # Unwrap the single-key dict → list of rows
    if isinstance(decoded, dict) and "malefni_tg" in decoded:
        return decoded["malefni_tg"]
    return decoded


def fetch_file_list(client: httpx.Client) -> list[dict]:
    r = client.get(f"{API_BASE}/api/FJS/Data/skrar")
    r.raise_for_status()
    decoded = _decode_data(r.json())
    if isinstance(decoded, dict) and "skrar" in decoded:
        return decoded["skrar"]
    return decoded


def download_file(client: httpx.Client, name: str) -> tuple[bytes, str]:
    url = f"{API_BASE}/api/Files/Rikisreikningur/{urllib.parse.quote(name)}"
    r = client.get(url)
    r.raise_for_status()
    return r.content, url


def cmd_timabil(args):
    with _client() as c:
        t = fetch_timabil(c)
    print(f"ár     : {t.get('ar')}")
    print(f"tímabil: {t.get('timabil')}  (13 = full year, 06 = mid-year, …)")


def cmd_summary(args):
    with _client() as c:
        data = fetch_tekjur_og_gjold(c)

    afkoma = sorted(data["afkoma"], key=lambda r: r["ar"])
    print("Afkoma (surplus/deficit) — ISK billion:")
    for r in afkoma:
        tekjur = r["tekjur"] / 1e9
        gjold = r["gjold"] / 1e9
        net = r["afkoma"] / 1e9
        print(f"  {r['ar']}   rev={tekjur:>8.1f}   exp={gjold:>8.1f}   net={net:>+8.1f}")

    # Persist full CSV
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "rikisreikningur_summary.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ar", "tekjur", "gjold", "afkoma"])
        for r in afkoma:
            w.writerow([r["ar"], r["tekjur"], r["gjold"], r["afkoma"]])
    print(f"\n→ {out}")

    # Category breakdown CSV
    out2 = PROCESSED_DIR / "rikisreikningur_tekjur_gjold.csv"
    with out2.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["timabil_ar", "timabil", "tegund_numer", "tegund", "texti", "samtals"],
        )
        w.writeheader()
        w.writerows(data["tekjur_gjold"])
    print(f"→ {out2}  ({len(data['tekjur_gjold'])} rows)")


def cmd_malefni(args):
    with _client() as c:
        rows = fetch_malefni(c)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "rikisreikningur_malefni.csv"
    fields = sorted({k for r in rows for k in r.keys()})
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows → {out}")
    # Summary: distinct málefnasvið and years
    svid = sorted({(r["malefnasvid_numer"], r["malefnasvid_heiti"]) for r in rows})
    years = sorted({r["timabil_ar"] for r in rows})
    print(f"{len(svid)} málefnasvið · years {min(years)}–{max(years)}")


def cmd_files(args):
    with _client() as c:
        skrar = fetch_file_list(c)
    skrar = sorted(skrar, key=lambda s: (s.get("ar", 0), s.get("nafn", "")))
    for s in skrar:
        print(f"  {s.get('ar',''):<6} {s.get('tegund','?'):<5} {s.get('nafn','')}")
    print(f"\n{len(skrar)} files")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "rikisreikningur_files.csv"
    fields = sorted({k for s in skrar for k in s.keys()})
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(skrar)
    print(f"→ {out}")


def cmd_download(args):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"\s+", " ", args.name).strip()
    dest = RAW_DIR / safe
    with _client() as c:
        content, url = download_file(c, safe)
    dest.write_bytes(content)
    print(f"downloaded {len(content)} bytes → {dest}")
    print(f"  source: {url}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("timabil").set_defaults(func=cmd_timabil)
    sub.add_parser("summary").set_defaults(func=cmd_summary)
    sub.add_parser("malefni").set_defaults(func=cmd_malefni)
    sub.add_parser("files").set_defaults(func=cmd_files)

    p_d = sub.add_parser("download")
    p_d.add_argument("--name", required=True, help="File name from `files` listing")
    p_d.set_defaults(func=cmd_download)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

"""Reykjavík procurement portal (utbod.reykjavik.is, In-Tend) — tender register 2017–present.

utbod.reykjavik.is redirects to an In-Tend SPA at supplier.in-tend.co.uk/reykjavik.
Its JSON backend answers without login for two things:

  - POST /Tenders/GetTendersList?list=current  — tenders open right now
  - GET  /Tenders/GetProjectFields?projectId=N — the public notice fields of ANY
    project, open or closed, by sequential project id (1 = 2017 test project)

`fetch` walks project ids 1..N and caches each response; closed projects are
immutable, so only projects whose document deadline is in the future (or
unseen ids) are re-fetched. Tender documents, bids and award values need a
supplier login and are NOT harvested.

Usage:
    uv run python scripts/utbod_reykjavik.py                 # = fetch
    uv run python scripts/utbod_reykjavik.py list            # current tenders
    uv run python scripts/utbod_reykjavik.py fetch [--force] [--max-id N]
    uv run python scripts/utbod_reykjavik.py search 'ræst'   # regex on title/description
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import httpx
import polars as pl

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "utbod_reykjavik" / "projects"
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUT = PROCESSED_DIR / "utbod_reykjavik_projects.csv"

BASE = "https://supplier.in-tend.co.uk/reykjavik"
UA = "icelandic-data/1.0 (+https://github.com/jokull/icelandic-data)"
TIMEOUT = 60
WORKERS = 4  # polite: ~0.35 s per request, 1.6k ids ≈ 2–3 min
STOP_AFTER_EMPTY = 25  # consecutive empty ids past the highest known id = end

# English labels (lng=en-GB) are stable; Icelandic labels vary with translation.
FIELD_MAP = {
    "Title": "title",
    "Description": "description",
    "Reference": "reference",
    "Award": "award_date",
    "Estimated Value": "estimated_value",
    "Qualifications": "qualifications",
    "Contact": "contact",
    "OJEU Notice": "ojeu_notice",
    "Extension Clause Date": "extension_clause_date",
    "Date documents can be requested until": "docs_available_until",
    "Customer": "customer",
    "CPV Code": "cpv",
}
DATE_COLS = ["award_date", "extension_clause_date", "docs_available_until"]
NULL_DATE = "1899-01-01T00:00:00"  # In-Tend's sentinel for "not set"


def client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA, "Accept": "application/json"})


def parse_fields(project_id: int, fields: list[dict]) -> dict | None:
    """Turn In-Tend's [{key, value}] list into a flat record; None if the id is empty."""
    rec: dict = {"project_id": project_id}
    extra = {}
    for f in fields:
        key, val = f.get("key"), f.get("value")
        if isinstance(val, str):
            val = val.strip()
        if val in ("", NULL_DATE, None):
            val = None
        col = FIELD_MAP.get(key)
        if col:
            rec[col] = val
        elif key:
            extra[key] = val
    if not rec.get("title"):
        return None
    if extra:
        rec["extra_fields"] = json.dumps(extra, ensure_ascii=False)
    # Most titles start with the city's reference number ("16338 - ...").
    if not rec.get("reference"):
        m = re.match(r"\s*(\d{4,6})\b", rec["title"])
        rec["reference"] = m.group(1) if m else None
    return rec


def fetch_project(http: httpx.Client, project_id: int) -> list[dict]:
    r = http.get(
        f"{BASE}/Tenders/GetProjectFields",
        params={"summary": "false", "projectId": project_id, "lng": "en-GB"},
    )
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def cache_path(project_id: int) -> Path:
    return RAW_DIR / f"{project_id}.json"


def is_frozen(project_id: int) -> bool:
    """Cached and its document deadline has passed → immutable, skip."""
    p = cache_path(project_id)
    if not p.exists():
        return False
    rec = parse_fields(project_id, json.loads(p.read_text(encoding="utf-8")))
    if rec is None:
        return False  # empty ids at the frontier may get filled later
    until = rec.get("docs_available_until")
    return bool(until) and until < datetime.now().isoformat()


def current_tenders(http: httpx.Client) -> list[dict]:
    out, page = [], 0
    while True:
        r = http.post(
            f"{BASE}/Tenders/GetTendersList",
            params={"list": "current", "customerId": -1},
            json={"page": page, "orderBy": "", "orderByDescending": False, "pageLength": 50, "SearchText": ""},
        )
        r.raise_for_status()
        payload = r.json()
        out.extend(payload["data"])
        if len(out) >= payload["totalResults"] or not payload["data"]:
            return out
        page += 1


def cmd_list(args: argparse.Namespace) -> None:
    with client() as http:
        rows = current_tenders(http)
    for t in rows:
        print(f"{t['projectID']:>5}  {t.get('cpv') or '':<12} {t['offsetDateDocsAvailableUntil'][:10]}  {t['title']}")
    print(f"  {len(rows)} current tenders")


def cmd_fetch(args: argparse.Namespace) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with client() as http:
        frontier = max((t["projectID"] for t in current_tenders(http)), default=0)
        max_id = args.max_id or frontier + STOP_AFTER_EMPTY
        ids = [i for i in range(1, max_id + 1) if args.force or not is_frozen(i)]
        print(f"  highest current project id {frontier}; fetching {len(ids)} of {max_id} ids")

        failed: list[tuple[int, str]] = []

        def work(i: int) -> None:
            try:
                fields = fetch_project(http, i)
            except httpx.HTTPError as exc:
                failed.append((i, f"{type(exc).__name__}: {exc}"))
                return
            cache_path(i).write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")

        t0 = time.time()
        with ThreadPoolExecutor(WORKERS) as pool:
            for n, _ in enumerate(pool.map(work, ids), 1):
                if n % 200 == 0:
                    print(f"  {n}/{len(ids)} ({time.time() - t0:.0f}s)")

    records = []
    for p in sorted(RAW_DIR.glob("*.json"), key=lambda p: int(p.stem)):
        rec = parse_fields(int(p.stem), json.loads(p.read_text(encoding="utf-8")))
        if rec:
            records.append(rec)
    df = to_frame(records)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.write_csv(OUTPUT)
    print(f"  {df.height} projects -> {OUTPUT.relative_to(ROOT)}")
    if failed:
        print(f"  {len(failed)} ids failed (re-run to retry):", file=sys.stderr)
        for i, why in failed[:20]:
            print(f"    {i}: {why}", file=sys.stderr)
        sys.exit(1)


def to_frame(records: list[dict]) -> pl.DataFrame:
    cols = ["project_id", *FIELD_MAP.values(), "extra_fields"]
    df = pl.DataFrame([{c: r.get(c) for c in cols} for r in records], schema={c: pl.Utf8 for c in cols})
    return (
        df.with_columns(
            pl.col("project_id").cast(pl.Int64),
            *[pl.col(c).str.to_datetime("%Y-%m-%dT%H:%M:%S", strict=False) for c in DATE_COLS],
        )
        .with_columns(pl.col("docs_available_until").dt.year().alias("year"))
        .unique(subset=["project_id"], keep="last")
        .sort("project_id")
    )


def cmd_search(args: argparse.Namespace) -> None:
    if not OUTPUT.exists():
        sys.exit(f"{OUTPUT} missing — run fetch first")
    df = pl.read_csv(OUTPUT, try_parse_dates=True)
    pat = f"(?i){args.pattern}"
    hits = df.filter(pl.col("title").str.contains(pat) | pl.col("description").fill_null("").str.contains(pat))
    for r in hits.iter_rows(named=True):
        print(f"{r['project_id']:>5}  {str(r['docs_available_until'])[:10]}  {r['cpv'] or '':<12} {r['title']}")
    print(f"  {hits.height} matches")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers()
    p = sub.add_parser("list", help="tenders open right now")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("fetch", help="harvest all project notices (cached)")
    p.add_argument("--force", action="store_true", help="re-fetch frozen projects too")
    p.add_argument("--max-id", type=int, help="highest project id to try")
    p.set_defaults(func=cmd_fetch)
    p = sub.add_parser("search", help="regex over title and description")
    p.add_argument("pattern")
    p.set_defaults(func=cmd_search)
    args = parser.parse_args()
    if not hasattr(args, "func"):
        args = parser.parse_args(["fetch"])
    args.func(args)


if __name__ == "__main__":
    main()

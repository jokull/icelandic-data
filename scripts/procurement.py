"""Fetch and process Icelandic public procurement data from TED API and OCDS bulk data."""

import argparse
import csv
import gzip
import json
import sys
from pathlib import Path

import httpx

TED_API_URL = "https://api.ted.europa.eu/v3/notices/search"
OCDS_DOWNLOAD_URL = "https://data.open-contracting.org/en/publication/57/download?name=full.jsonl.gz"
RAW_DIR = Path("data/raw/procurement")
PROCESSED_DIR = Path("data/processed")


def download_ocds(args):
    """Download OCDS bulk JSONL data for Iceland."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    output = RAW_DIR / "ocds_iceland.jsonl"

    print("Downloading OCDS data...", file=sys.stderr)
    with httpx.stream("GET", OCDS_DOWNLOAD_URL, follow_redirects=True, timeout=120) as resp:
        resp.raise_for_status()
        gz_path = RAW_DIR / "full.jsonl.gz"
        with open(gz_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=8192):
                f.write(chunk)

    print("Decompressing...", file=sys.stderr)
    with gzip.open(gz_path, "rt", encoding="utf-8") as gz, open(output, "w") as out:
        count = 0
        for line in gz:
            out.write(line)
            count += 1

    gz_path.unlink()
    print(f"Wrote {count} records to {output}", file=sys.stderr)


def load_ocds():
    """Load OCDS JSONL file. Returns list of release dicts."""
    path = RAW_DIR / "ocds_iceland.jsonl"
    if not path.exists():
        print(f"OCDS data not found at {path}. Run: uv run python scripts/procurement.py download-ocds", file=sys.stderr)
        sys.exit(1)
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _ted_field(notice: dict, field: str) -> str:
    """Extract a display value from a TED API notice field.

    TED fields can be: plain strings, lists, or multilingual dicts like
    {"eng": ["value"]} or {"mul": ["value"]}.
    """
    val = notice.get(field)
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return str(val[0]) if val else ""
    if isinstance(val, dict):
        # Try eng first, then mul, then first available key
        for key in ("eng", "mul"):
            if key in val:
                inner = val[key]
                if isinstance(inner, list):
                    return str(inner[0]) if inner else ""
                return str(inner)
        # Fallback: first value
        for inner in val.values():
            if isinstance(inner, list):
                return str(inner[0]) if inner else ""
            return str(inner)
    return str(val)


def search_ted(args):
    """Search TED API for Icelandic tenders."""
    parts = ["organisation-country-buyer=ISL"]
    if args.buyer:
        parts.append(f'organisation-name-buyer="{args.buyer}*"')
    if args.cpv:
        parts.append(f"classification-cpv={args.cpv}")
    if args.date_from:
        parts.append(f"publication-date>={args.date_from}")
    if args.date_to:
        parts.append(f"publication-date<={args.date_to}")

    query = " AND ".join(parts)
    body = {
        "query": query,
        "fields": [
            "notice-title",
            "publication-date",
            "organisation-name-buyer",
            "buyer-city",
            "classification-cpv",
            "tender-value",
            "tender-value-cur",
            "description-lot",
        ],
        "limit": args.limit,
        "page": args.page,
    }

    print(f"Query: {query}", file=sys.stderr)
    resp = httpx.post(TED_API_URL, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    notices = data.get("notices", [])
    total = data.get("total", 0)
    print(f"Found {total} total, showing {len(notices)}", file=sys.stderr)

    if not notices:
        print("No results.", file=sys.stderr)
        return

    # Print as table
    print(f"{'Date':<12} {'Buyer':<30} {'Title':<50} {'Value':>15} {'CPV':<10}")
    print("-" * 120)
    for n in notices:
        date = str(n.get("publication-date", ""))[:10]
        buyer = _ted_field(n, "organisation-name-buyer")[:29]
        title = _ted_field(n, "notice-title")[:49]
        value = _ted_field(n, "tender-value")
        cur = _ted_field(n, "tender-value-cur")
        cpv = _ted_field(n, "classification-cpv")[:9]
        val_str = f"{value} {cur}" if value else ""
        print(f"{date:<12} {buyer:<30} {title:<50} {val_str:>15} {cpv:<10}")


def extract_awards(args):
    """Extract award data from OCDS, flatten to CSV."""
    records = load_ocds()

    rows = []
    for rec in records:
        buyer_name = rec.get("buyer", {}).get("name", "")

        if args.buyer and args.buyer.lower() not in buyer_name.lower():
            continue

        tender = rec.get("tender", {})
        title = tender.get("title", "")
        ocid = rec.get("ocid", "")

        # Get CPV from tender items
        cpv = ""
        for item in tender.get("items", []):
            cl = item.get("classification", {})
            if cl.get("scheme") == "CPV":
                cpv = cl.get("id", "")
                break

        for award in rec.get("awards", []):
            award_value = award.get("value", {})
            amount = award_value.get("amount")
            currency = award_value.get("currency", "")

            for supplier in award.get("suppliers", []):
                rows.append({
                    "ocid": ocid,
                    "title": title,
                    "buyer": buyer_name,
                    "supplier": supplier.get("name", ""),
                    "value": amount if amount is not None else "",
                    "currency": currency,
                    "cpv": cpv,
                    "date": rec.get("date", ""),
                })

    if not rows:
        print("No awards found matching filters.", file=sys.stderr)
        return

    # Sort by value descending
    rows.sort(key=lambda r: float(r["value"]) if r["value"] != "" else 0, reverse=True)

    fieldnames = ["ocid", "title", "buyer", "supplier", "value", "currency", "cpv", "date"]

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {len(rows)} awards to {output}", file=sys.stderr)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        print(f"\n{len(rows)} awards total", file=sys.stderr)


def list_buyers(args):
    """List all buyers with tender counts from OCDS data."""
    records = load_ocds()

    buyer_counts: dict[str, int] = {}
    for rec in records:
        buyer = rec.get("buyer", {}).get("name", "Unknown")
        buyer_counts[buyer] = buyer_counts.get(buyer, 0) + 1

    ranked = sorted(buyer_counts.items(), key=lambda x: x[1], reverse=True)

    limit = args.limit if hasattr(args, "limit") else 30
    print(f"{'Buyer':<50} {'Tenders':>8}")
    print("-" * 60)
    for name, count in ranked[:limit]:
        print(f"{name:<50} {count:>8}")
    print(f"\n{len(buyer_counts)} unique buyers, {len(records)} total tenders", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Icelandic procurement data (TED API + OCDS)")
    sub = parser.add_subparsers(dest="command", required=True)

    # download-ocds
    sub.add_parser("download-ocds", help="Download OCDS bulk JSONL for Iceland")

    # search (TED API)
    p_search = sub.add_parser("search", help="Search TED API for Icelandic tenders")
    p_search.add_argument("--buyer", help="Filter by buyer name (prefix match)")
    p_search.add_argument("--cpv", help="Filter by CPV code")
    p_search.add_argument("--date-from", help="Publication date from (YYYYMMDD)")
    p_search.add_argument("--date-to", help="Publication date to (YYYYMMDD)")
    p_search.add_argument("--limit", type=int, default=20, help="Results per page (default 20)")
    p_search.add_argument("--page", type=int, default=1, help="Page number (default 1)")

    # awards (OCDS)
    p_awards = sub.add_parser("awards", help="Extract awards from OCDS data")
    p_awards.add_argument("--buyer", help="Filter by buyer name (substring match)")
    p_awards.add_argument("-o", "--output", help="Output CSV path (default: stdout)")

    # buyers (OCDS)
    p_buyers = sub.add_parser("buyers", help="List buyers with tender counts from OCDS")
    p_buyers.add_argument("--limit", type=int, default=30, help="Number of buyers to show")

    args = parser.parse_args()

    if args.command == "download-ocds":
        download_ocds(args)
    elif args.command == "search":
        search_ted(args)
    elif args.command == "awards":
        extract_awards(args)
    elif args.command == "buyers":
        list_buyers(args)


if __name__ == "__main__":
    main()

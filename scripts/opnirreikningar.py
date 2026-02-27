"""Fetch government invoice data from opnirreikningar.is (Open Accounts of the State)."""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote

import httpx

BASE_URL = "https://opnirreikningar.is"
HEADERS = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}

# DataTables column spec — abbreviated form that the API accepts
COLUMNS_QS = "&".join(
    f"columns[{i}][data]={name}"
    for i, name in enumerate(["org_name", "check_date", "vendor_name", "invoice_amount", "check_amount"])
)

CSV_FIELDS = [
    "org_name",
    "check_date",
    "check_amount",
    "vendor_name",
    "invoice_num",
    "invoice_date",
    "invoice_amount",
    "invoice_description",
]


def _to_dd_mm_yyyy(iso: str) -> str:
    """Convert YYYY-MM-DD → DD.MM.YYYY for the API."""
    d = date.fromisoformat(iso)
    return d.strftime("%d.%m.%Y")


def _build_search_url(*, org_id="", org_text="", vendor_id="", fra="", til="", start=0, length=500):
    """Build the DataTables pagination search URL."""
    params = (
        f"vendor_id={vendor_id}&type_id=&org_id={org_id}"
        f"&timabil_fra={fra}&timabil_til={til}"
    )
    if org_text:
        params += f"&org_text={quote(org_text)}"
    params += f"&draw=1&{COLUMNS_QS}&start={start}&length={length}"
    params += "&order[0][column]=1&order[0][dir]=desc"
    return f"{BASE_URL}/data_pagination_search?{params}"


def search_org(args):
    """Search for government organizations."""
    resp = httpx.get(f"{BASE_URL}/rest/org", params={"term": args.term}, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    if not data:
        print("No results.", file=sys.stderr)
        return
    for item in data:
        print(f"{item['id']:>8}  {item['text']}")


def search_vendor(args):
    """Search for vendors by name."""
    resp = httpx.get(f"{BASE_URL}/rest/vendor", params={"term": args.term}, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    if not data:
        print("No results.", file=sys.stderr)
        return
    for item in data:
        print(f"{item['id']:>12}  {item['text']}")


def _paginate(client, *, org_id="", org_text="", vendor_id="", fra, til):
    """Paginate through all invoice results. Yields row dicts.

    Uses length=50 to avoid the server's 51-row first-page cap which
    silently truncates larger pages. Deduplicates by unique_id.
    """
    seen: set[str] = set()
    start = 0
    length = 50
    while True:
        url = _build_search_url(
            org_id=org_id, org_text=org_text, vendor_id=vendor_id,
            fra=fra, til=til, start=start, length=length,
        )
        print(f"Fetching start={start}...", file=sys.stderr)
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            break
        new_count = 0
        for row in data:
            uid = row.get("unique_id", "")
            if uid not in seen:
                seen.add(uid)
                yield row
                new_count += 1
        if new_count == 0:
            break
        start += len(data)


def fetch(args):
    """Fetch invoices with pagination, write CSV."""
    if not args.org and not args.vendor:
        print("Warning: without --org or --vendor, API caps results at ~51 rows. Use --org for full pagination.", file=sys.stderr)
    fra = _to_dd_mm_yyyy(args.date_from)
    til = _to_dd_mm_yyyy(args.date_to)
    org_id = str(args.org) if args.org else ""
    vendor_id = args.vendor or ""
    org_text = args.org_text or ""

    rows = []
    with httpx.Client(headers=HEADERS, timeout=30) as client:
        for row in _paginate(client, org_id=org_id, org_text=org_text, vendor_id=vendor_id, fra=fra, til=til):
            rows.append({
                "org_name": row.get("org_name", ""),
                "check_date": row.get("check_date", ""),
                "check_amount": row.get("check_amount", ""),
                "vendor_name": row.get("vendor_name", ""),
                "invoice_num": row.get("invoice_num", ""),
                "invoice_date": row.get("invoice_date", ""),
                "invoice_amount": row.get("invoice_amount", ""),
                "invoice_description": row.get("invoice_description", ""),
            })

    if not rows:
        print("No invoices found.", file=sys.stderr)
        return

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Wrote {len(rows)} invoices to {output}", file=sys.stderr)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        print(f"\n{len(rows)} invoices total", file=sys.stderr)


def top_vendors(args):
    """Show top vendors by total invoice amount for an org/year."""
    fra = _to_dd_mm_yyyy(f"{args.year}-01-01")
    til = _to_dd_mm_yyyy(f"{args.year}-12-31")
    org_id = str(args.org)

    vendor_totals: dict[str, int] = defaultdict(int)
    vendor_counts: dict[str, int] = defaultdict(int)

    with httpx.Client(headers=HEADERS, timeout=30) as client:
        for row in _paginate(client, org_id=org_id, fra=fra, til=til):
            vendor = row.get("vendor_name", "Unknown")
            amount = row.get("invoice_amount", 0)
            if isinstance(amount, str):
                amount = int(amount.replace(".", "").replace(",", "").strip() or "0")
            vendor_totals[vendor] += amount
            vendor_counts[vendor] += 1

    if not vendor_totals:
        print("No invoices found.", file=sys.stderr)
        return

    ranked = sorted(vendor_totals.items(), key=lambda x: x[1], reverse=True)
    limit = args.limit

    print(f"{'Vendor':<45} {'Total (ISK)':>15} {'Invoices':>10}")
    print("-" * 72)
    for vendor, total in ranked[:limit]:
        count = vendor_counts[vendor]
        print(f"{vendor[:44]:<45} {total:>15,} {count:>10}")
    print(f"\n{len(vendor_totals)} unique vendors", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Government invoice data from opnirreikningar.is")
    sub = parser.add_subparsers(dest="command", required=True)

    # search-org
    p_org = sub.add_parser("search-org", help="Look up government org by name")
    p_org.add_argument("term", help="Search term")

    # search-vendor
    p_vendor = sub.add_parser("search-vendor", help="Look up vendor by name")
    p_vendor.add_argument("term", help="Search term")

    # fetch
    p_fetch = sub.add_parser("fetch", help="Fetch invoices to CSV")
    p_fetch.add_argument("--org", type=int, help="Organization ID")
    p_fetch.add_argument("--org-text", help="Org text label (e.g. '14412 - Veðurstofa Íslands')")
    p_fetch.add_argument("--vendor", help="Vendor kennitala")
    p_fetch.add_argument("--from", dest="date_from", required=True, help="Start date (YYYY-MM-DD)")
    p_fetch.add_argument("--to", dest="date_to", required=True, help="End date (YYYY-MM-DD)")
    p_fetch.add_argument("-o", "--output", help="Output CSV path (default: stdout)")

    # top-vendors
    p_top = sub.add_parser("top-vendors", help="Top vendors by amount for an org/year")
    p_top.add_argument("--org", type=int, required=True, help="Organization ID")
    p_top.add_argument("--year", type=int, required=True, help="Year")
    p_top.add_argument("--limit", type=int, default=20, help="Number of vendors to show")

    args = parser.parse_args()

    if args.command == "search-org":
        search_org(args)
    elif args.command == "search-vendor":
        search_vendor(args)
    elif args.command == "fetch":
        fetch(args)
    elif args.command == "top-vendors":
        top_vendors(args)


if __name__ == "__main__":
    main()

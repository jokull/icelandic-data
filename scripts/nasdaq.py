"""
Nasdaq Iceland API wrapper.

Handles URL encoding, pagination, and common queries.

Usage:
    uv run python scripts/nasdaq.py companies                    # List all companies
    uv run python scripts/nasdaq.py categories                   # List all categories
    uv run python scripts/nasdaq.py search "Arion banki"         # Search announcements
    uv run python scripts/nasdaq.py search --company "Arion banki hf." --category "Ársreikningur"
    uv run python scripts/nasdaq.py search --company "Icelandair Group hf." --from 2024-01-01
    uv run python scripts/nasdaq.py download <disclosure_id>     # Download attachments
"""

import httpx
import json
import sys
from pathlib import Path
from urllib.parse import quote

BASE_URL = "https://api.news.eu.nasdaq.com/news"
DATA_DIR = Path(__file__).parent.parent / "data" / "raw" / "nasdaq"


def query(
    company: str | None = None,
    category: str | None = None,
    freetext: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    market: str = "Main Market, Iceland",
    global_name: str = "NordicMainMarkets",
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Query announcements with automatic URL encoding."""
    params = {
        "globalGroup": "exchangeNotice",
        "globalName": global_name,
        "market": market,
        "limit": limit,
        "start": offset,
        "dir": "DESC",
        "displayLanguage": "is",
        "dateMask": "yyyy-MM-dd HH:mm:ss",
        "countResults": "true",
    }

    if company:
        params["company"] = company
    if category:
        params["cnsCategory"] = category
    if freetext:
        params["freeText"] = freetext
    if from_date:
        params["fromDate"] = from_date
    if to_date:
        params["toDate"] = to_date

    resp = httpx.get(f"{BASE_URL}/query.action", params=params)
    resp.raise_for_status()
    return resp.json()


def query_all(
    company: str | None = None,
    category: str | None = None,
    freetext: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    market: str = "Main Market, Iceland",
    global_name: str = "NordicMainMarkets",
    max_results: int = 1000,
) -> list[dict]:
    """Query all matching announcements with automatic pagination."""
    all_items = []
    offset = 0
    limit = 100

    while len(all_items) < max_results:
        data = query(
            company=company,
            category=category,
            freetext=freetext,
            from_date=from_date,
            to_date=to_date,
            market=market,
            global_name=global_name,
            limit=limit,
            offset=offset,
        )

        items = data.get("results", {}).get("item", [])
        if not items:
            break

        all_items.extend(items)
        offset += limit

        total = data.get("count", 0)
        if offset >= total:
            break

    return all_items[:max_results]


def get_metadata(
    result_type: str,
    market: str = "Main Market, Iceland",
    global_name: str = "NordicMainMarkets",
    company: str | None = None,
) -> list[str]:
    """Get available filter values (companies, categories)."""
    params = {
        "globalGroup": "exchangeNotice",
        "globalName": global_name,
        "market": market,
        "resultType": result_type,
        "displayLanguage": "is",
    }
    if company:
        params["company"] = company

    resp = httpx.get(f"{BASE_URL}/metadata.action", params=params)
    resp.raise_for_status()
    data = resp.json()
    return [fact["id"] for fact in data.get("facts", [])]


def list_companies(market: str = "Main Market, Iceland", global_name: str = "NordicMainMarkets") -> list[str]:
    """List all companies with announcements."""
    return get_metadata("company", market=market, global_name=global_name)


def list_categories(market: str = "Main Market, Iceland", global_name: str = "NordicMainMarkets", company: str | None = None) -> list[str]:
    """List all announcement categories."""
    return get_metadata("cnscategory", market=market, global_name=global_name, company=company)


def download_attachment(url: str, output_dir: Path | None = None) -> Path:
    """Download an attachment and return the path."""
    output_dir = output_dir or DATA_DIR / "attachments"
    output_dir.mkdir(parents=True, exist_ok=True)

    resp = httpx.get(url)
    resp.raise_for_status()

    # Get filename from header or URL
    filename = resp.headers.get("x-amz-meta-filename", url.split("/")[-1])
    output_path = output_dir / filename

    output_path.write_bytes(resp.content)
    return output_path


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Nasdaq Iceland API wrapper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # companies
    companies_parser = subparsers.add_parser("companies", help="List companies")
    companies_parser.add_argument("--market", default="Main Market, Iceland")
    companies_parser.add_argument("--first-north", action="store_true", help="Use First North Iceland")

    # categories
    categories_parser = subparsers.add_parser("categories", help="List categories")
    categories_parser.add_argument("--company", help="Filter categories for specific company")
    categories_parser.add_argument("--market", default="Main Market, Iceland")

    # search
    search_parser = subparsers.add_parser("search", help="Search announcements")
    search_parser.add_argument("query", nargs="?", help="Free text search")
    search_parser.add_argument("--company", "-c", help="Company name (exact match)")
    search_parser.add_argument("--category", "-k", help="Category name")
    search_parser.add_argument("--from", dest="from_date", help="From date (YYYY-MM-DD)")
    search_parser.add_argument("--to", dest="to_date", help="To date (YYYY-MM-DD)")
    search_parser.add_argument("--market", default="Main Market, Iceland")
    search_parser.add_argument("--first-north", action="store_true")
    search_parser.add_argument("--limit", type=int, default=100)
    search_parser.add_argument("--output", "-o", help="Output file (JSON)")

    # download
    download_parser = subparsers.add_parser("download", help="Download attachments for announcement")
    download_parser.add_argument("disclosure_id", help="Disclosure ID")

    args = parser.parse_args()

    if args.command == "companies":
        global_name = "NordicFirstNorth" if args.first_north else "NordicMainMarkets"
        market = "First North Iceland" if args.first_north else args.market
        companies = list_companies(market=market, global_name=global_name)
        for c in sorted(companies):
            print(c)

    elif args.command == "categories":
        categories = list_categories(market=args.market, company=args.company)
        for c in sorted(categories):
            print(c)

    elif args.command == "search":
        global_name = "NordicFirstNorth" if args.first_north else "NordicMainMarkets"
        market = "First North Iceland" if args.first_north else args.market

        results = query_all(
            company=args.company,
            category=args.category,
            freetext=args.query,
            from_date=args.from_date,
            to_date=args.to_date,
            market=market,
            global_name=global_name,
            max_results=args.limit,
        )

        output = [
            {
                "date": r["releaseTime"],
                "company": r["company"],
                "headline": r["headline"],
                "category": r["cnsCategory"],
                "url": r["messageUrl"],
                "attachments": [a["attachmentUrl"] for a in r.get("attachment", [])],
            }
            for r in results
        ]

        if args.output:
            Path(args.output).write_text(json.dumps(output, indent=2, ensure_ascii=False))
            print(f"Wrote {len(output)} results to {args.output}")
        else:
            print(json.dumps(output, indent=2, ensure_ascii=False))

    elif args.command == "download":
        # First get the announcement to find attachments
        # This is a simplified version - in practice you'd query by disclosure_id
        print(f"Download not yet implemented for disclosure_id={args.disclosure_id}")
        print("Use the attachment URL directly with curl")


if __name__ == "__main__":
    main()

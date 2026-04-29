"""Landlæknir (Directorate of Health) dashboards — Mælaborð catalog + Power BI scraper.

Scrapes the ~30 Power BI dashboards published by Embætti landlæknis
at https://island.is/maelabord. All dashboards are public `/view?r=...` embeds
sharing tenant `4d762ac0-6205-42ce-b964-c3b8958fd4a9`.

Usage:
    uv run python scripts/landlaeknir.py list
    uv run python scripts/landlaeknir.py fetch --slug mortis
    uv run python scripts/landlaeknir.py fetch --all
"""
import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path

import polars as pl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

TENANT = "4d762ac0-6205-42ce-b964-c3b8958fd4a9"

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "landlaeknir"
PROCESSED_DIR = Path(__file__).parent.parent / "data" / "processed"

CATALOG: list[dict] = [
    # category, slug, name, report_key
    ("lydheilsa", "lydheilsuvaktin", "Lýðheilsuvaktin", "e96fb72e-64c7-40b9-b413-9880b6d3ebb6"),
    ("lydheilsa", "lydheilsuvisar", "Lýðheilsuvísar", "b844ee2b-a5ac-47e3-8c32-fd4c9260a7b3"),
    ("lydheilsa", "reykingar", "Reykingar", "8a8c91a6-8baa-4a92-91f7-c8bbb09a61cf"),
    ("lyfjanotkun", "lyfjanotkun", "Lyfjanotkun", "91dbfdc1-b502-412d-b5b9-ed9195d13cc5"),
    ("lyfjanotkun", "adhd_lyf", "ADHD-lyfja", "5964b5b1-e090-4295-876a-16d7818f5d89"),
    ("lyfjanotkun", "thunglyndislyf", "Þunglyndislyfja", "da30ebd3-fdb3-4f61-85b2-c0eaf2475816"),
    ("lyfjanotkun", "opioid", "Ópíóíða", "7de4f8d0-1d91-4e36-9ada-d708069663be"),
    ("lyfjanotkun", "svefnlyf", "Svefnlyfja og slævandi lyfja", "4c04de98-4ba9-499e-9de2-28e1169ca81f"),
    ("lyfjanotkun", "syklalyf", "Sýklalyfja", "8ab229cd-6dc2-41b5-b472-b2e9bd62dcdf"),
    ("danarorsakir", "mortis", "Mortis", "9762f31f-75d5-44a0-84f4-2748ada887a5"),
    ("danarorsakir", "umframdanartidni", "Umframdánartíðni", "8434975c-221d-4cf8-be41-b3a018a341c8"),
    ("danarorsakir", "sjalfsvig", "Sjálfsvíg", "7099a77d-3bcb-4ecc-b3ad-555816b6d199"),
    ("danarorsakir", "lyfjatengd_andlat", "Lyfjatengd andlát", "4b1b3b1f-627a-4b65-9088-35a5be7a0d80"),
    ("starfsfolk", "mannafli", "Mannafli í heilbrigðisþjónustu", "100a2e7c-8e70-4f4d-8931-3a18f7743b54"),
    ("thjonusta", "lykilvisar", "Lykilvísar heilbrigðisþjónustu", "3c7aff7a-d011-49c0-999b-42e8572b333d"),
    ("thjonusta", "sjukrahus", "Starfsemi sjúkrahúsa", "d397920c-ceeb-461e-8e5a-31637e0dfe2e"),
    ("thjonusta", "heilsugaesla", "Samskipti við heilsugæslu", "aaa2dbb1-509c-4440-a487-9f9b17f74d04"),
    ("thjonusta", "krabbameinsskimun", "Skimun fyrir krabbameini", "695fcc55-c9cf-48f9-8dea-05114188eacd"),
    ("thjonusta", "bid_skuradgerd", "Bið eftir skurðaðgerðum", "de0dd7d1-f6e8-4952-9dad-12f6d011338a"),
    ("thjonusta", "lidskiptadgerdir", "Liðskiptaaðgerðir", "66d4f15b-d403-41fb-9f46-11643f02f9ee"),
    ("thjonusta", "bid_hjukrunarrymi", "Bið eftir hjúkrunarrými", "f78159f5-1187-49eb-9b21-c3240b96659c"),
    ("thjonusta", "gaedi_hjukrunarheimili", "Gæði þjónustu á hjúkrunarheimilum", "7280e4c3-e418-45e7-8109-c52c9da328f7"),
    ("thjonusta", "tannheilsa_barna", "Tannheilsa barna", "9b56cbba-0997-47cb-819d-c4ad88c09083"),
    ("thjonusta", "alvarleg_atvik", "Alvarleg atvik", "288bcc93-e451-4227-855e-f517c45d8523"),
    ("thjonusta", "kvartanir", "Kvartanir", "6437ece5-4086-430e-9a6c-25e92c3f0cfd"),
    ("thjonusta", "rekstur", "Rekstur heilbrigðisþjónustu", "2b14022e-6e9a-4f31-a2e2-1ba08b7b9775"),
    ("thjonusta", "drg", "DRG mælaborð", "7da1376f-51a7-4129-83dd-47e1d68ad45b"),
    ("thjonusta", "acg", "ACG mælaborð", "f95fc235-5913-45a9-bd1a-c052c3f465b1"),
    ("sottvarnir", "smitsjukdomar", "Árlegur fjöldi smitsjúkdóma", "cd829644-4051-4a71-9571-e0ed60157d3b"),
    ("sottvarnir", "sti", "Lekandi, klamydía og sárasótt", "53f7eba1-f7bf-42dd-acad-9b4fa068cbd2"),
    ("sottvarnir", "ondunarfaeri", "Öndunarfærasýkingar", "f829b4c8-63dd-4cd3-9e37-1b1101e8e02d"),
    ("sottvarnir", "veirugreiningar", "Veirugreiningar", "656ffb3f-8a7f-4746-b921-4f6e364754ce"),
    ("sottvarnir", "bolusetningar_barna", "Þátttaka í bólusetningum barna", "608e169f-867c-4b00-9224-925e92b6a247"),
]


def embed_url(report_key: str) -> str:
    payload = {"k": report_key, "t": TENANT, "c": 8}
    token = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"https://app.powerbi.com/view?r={token}"


def cmd_list(args):
    rows = [
        {"category": cat, "slug": slug, "name": name, "report_key": key, "url": embed_url(key)}
        for cat, slug, name, key in CATALOG
    ]
    df = pl.DataFrame(rows)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "landlaeknir_catalog.csv"
    df.write_csv(out)
    for cat, slug, name, _ in CATALOG:
        print(f"  [{cat:14}] {slug:26} — {name}")
    print(f"\nTotal: {len(rows)} dashboards")
    print(f"Catalog: {out}")


async def _scrape_one(slug: str, url: str) -> list[dict]:
    from playwright.async_api import async_playwright

    results: list[dict] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            async def on_response(r):
                u = r.url.lower()
                if ("querydata" in u or "executequeries" in u) and r.status == 200:
                    try:
                        results.append(await r.json())
                    except Exception:
                        pass

            page.on("response", on_response)
            print(f"  [{slug}] loading {url}", file=sys.stderr)
            await page.goto(url, wait_until="networkidle", timeout=90000)
            await asyncio.sleep(15)
        finally:
            await browser.close()
    return results


def _save(slug: str, results: list[dict]) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{slug}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def cmd_fetch(args):
    by_slug = {slug: (name, key) for _, slug, name, key in CATALOG}
    if args.all:
        targets = list(by_slug.keys())
    elif args.slug:
        if args.slug not in by_slug:
            sys.exit(f"unknown slug: {args.slug}. run `list` to see options.")
        targets = [args.slug]
    else:
        sys.exit("specify --slug <name> or --all")

    for slug in targets:
        name, key = by_slug[slug]
        url = embed_url(key)
        print(f"\n=== {slug} — {name} ===", file=sys.stderr)
        try:
            results = asyncio.run(_scrape_one(slug, url))
        except Exception as e:
            print(f"  [error] {slug}: {e}", file=sys.stderr)
            continue
        out = _save(slug, results)
        print(f"  captured {len(results)} query responses → {out}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="Print dashboard catalog and write CSV")
    p_list.set_defaults(func=cmd_list)

    p_fetch = sub.add_parser("fetch", help="Scrape one or all dashboards")
    p_fetch.add_argument("--slug", help="Single dashboard slug (see `list`)")
    p_fetch.add_argument("--all", action="store_true", help="Scrape every dashboard")
    p_fetch.set_defaults(func=cmd_fetch)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

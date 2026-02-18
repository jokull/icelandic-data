# Nasdaq Iceland

Exchange notices for Icelandic listed companies (2000-present).

## Usage

```bash
# List companies
uv run python scripts/nasdaq.py companies
uv run python scripts/nasdaq.py companies --first-north

# List categories
uv run python scripts/nasdaq.py categories

# Search (handles Icelandic encoding automatically)
uv run python scripts/nasdaq.py search "arðgreiðsla"
uv run python scripts/nasdaq.py search --company "Arion banki hf." --category "Ársreikningur"
uv run python scripts/nasdaq.py search --company "Icelandair Group hf." --from 2024-01-01
uv run python scripts/nasdaq.py search --company "Fly Play hf." -o data/raw/nasdaq/play.json
```

## Markets

| Market | Companies | Flag |
|--------|-----------|------|
| Main Market Iceland | ~30 (banks, airlines, real estate) | default |
| First North Iceland | ~15 (growth companies) | `--first-north` |

## Key Categories

| Icelandic | English |
|-----------|---------|
| Ársreikningur | Annual report |
| Árshlutareikningur (Q1 og Q3) | Quarterly report |
| Innherjaupplýsingar | Insider information |
| Viðskipti stjórnenda | Manager transactions |
| Flöggun | Major shareholding |

## Output Format

```json
{
  "date": "2025-02-12 16:30:00",
  "company": "Arion banki hf.",
  "headline": "Afkoma Arion banka...",
  "category": "Ársreikningur",
  "url": "https://view.news.eu.nasdaq.com/...",
  "attachments": ["https://attachment.news.eu.nasdaq.com/..."]
}
```

Attachments are direct download URLs (PDFs, xBRL ZIPs). Download with curl:

```bash
# Download annual report PDF from attachment URL
curl -sL -o data/raw/nasdaq/reports/reitir_2024.pdf "https://attachment.news.eu.nasdaq.com/a5ca11199cd2e8f22cff77db1c9464763"
```

Note: The `download` subcommand is not yet implemented. Use attachment URLs from search results directly.

## Key Real Estate Companies

| Company | Type | Notes |
|---------|------|-------|
| Reitir fasteignafélag hf. | Commercial RE | ~226B ISK portfolio, 65% pension fund owned |
| Eik fasteignafélag hf. | Commercial RE | ~145B ISK portfolio, Langisjór takeover 2024 |
| Alma íbúðafélag hf. | Residential RE | ~88B ISK, Gíslason family controlled |
| FÍ Fasteignafélag slhf. | RE fund | Closed-end investment fund |

## Key Banks (mortgage portfolios)

| Bank | Kennitala |
|------|-----------|
| Arion banki hf. | 5810080150 |
| Íslandsbanki hf. | 4910083880 |
| Landsbankinn hf. | 4710044100 |

## Raw API (if needed)

```bash
# Companies
curl -s 'https://api.news.eu.nasdaq.com/news/metadata.action?globalGroup=exchangeNotice&globalName=NordicMainMarkets&market=Main+Market,+Iceland&resultType=company'

# Announcements (note: requires URL encoding for Icelandic)
curl -s 'https://api.news.eu.nasdaq.com/news/query.action?globalGroup=exchangeNotice&globalName=NordicMainMarkets&market=Main+Market,+Iceland&company=Arion+banki+hf.&limit=10'
```

Use the wrapper script instead - it handles encoding and pagination.

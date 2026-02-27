# Fuel — Icelandic Fuel Market

## Companies

| Retailer | Kennitala | Parent | Parent kt | Stations |
|----------|-----------|--------|-----------|----------|
| N1 ehf. | `4110033370` | Festi hf. | `5402062010` | ~100 |
| Olís ehf. | `5002693249` | Hagar hf. | `6702032120` | ~65 |
| Orkan IS ehf. | `6803190730` | Styrkás/SKEL | `6309212010` | ~75 |
| Atlantsolía ehf. | `5906023610` | Private | — | ~30 |

**Use parent kennitalas for consolidated financials** — fuel is a segment within diversified conglomerates.

Skeljungur ehf. (`6309212010`) is the wholesale fuel company under Styrkás — separate from Orkan retail but same ownership.

## Data Sources

### Gasvaktin — Daily retail prices
- **Repo:** github.com/gasvaktin/gasvaktin
- **Location:** `data/raw/gasvaktin/vaktin/trends.json`
- Company codes: `n1`=N1, `ol`=Olís, `or`=Orkan, `ox`=Orkan X, `ao`=Atlantsolía, `co`=Costco, `dn`=Dælan, `ob`=ÓB, `sk`=Skeljungur
- Data since April 2016, ~weekly observations per company

### Processing
```bash
uv run python scripts/fuel_prices.py
```
Outputs:
- `data/processed/fuel_prices_daily.csv` — all observations
- `data/processed/fuel_market_daily.csv` — market averages (major 4 retailers)
- `data/processed/fuel_prices_monthly.csv` — monthly by company
- `data/processed/fuel_price_spread.csv` — price spread between retailers

### Annual reports (skatturinn.is)
```bash
uv run python scripts/skatturinn.py download 5402062010 --year 2024  # Festi (N1 parent)
uv run python scripts/skatturinn.py download 6702032120 --year 2024  # Hagar (Olís parent)
uv run python scripts/skatturinn.py download 6309212010 --year 2024  # Skeljungur (Orkan wholesale)
```

**Note:** Festi has two reports per year (parent + consolidated). The download script picks typeid=1 first. For segment data, you may need the consolidated report (typeid=2).

### Hagar fiscal year
Hagar uses Feb-Jan fiscal year (e.g., "2024" = Feb 2023 – Jan 2024).

### Other data sources
- **IEA End-Use Prices** — cross-country fuel price comparison with tax breakdown
- **Samkeppniseftirlitið** — competition authority reports (2015 fuel market study, 2024 Festi fine)
- **Crude oil prices** — Brent ICE for margin computation

## Key Facts

- Festi fined 750M ISK in 2024 for violating 2018 N1 merger conditions
- N1 owns 60% of Olíudreifing ehf. (fuel distribution) — board must be independent per competition authority
- Hagar preparing to sell Olís stake in Olíudreifing and EAK (Keflavík airport fuel)
- Typical N1 premium over Atlantsolía: 5-13 ISK/L
- Skeljungur EBITDA/margin: 43.2% (2024)

## Caveats

1. **Conglomerate financials** — Festi and Hagar report consolidated; fuel is one segment. Segment data in note "Starfsþáttayfirlit".
2. **Skeljungur ≠ Orkan retail** — Skeljungur is wholesale/enterprise fuel; Orkan IS is retail. Same ownership (Styrkás) but separate entities.
3. **Gasvaktin coverage** — Not every station reports every day. Data may have gaps.
4. **Discount vs list prices** — Some companies offer discount (self-service) vs full-service pricing.

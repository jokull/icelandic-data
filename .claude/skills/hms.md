# HMS - Húsnæðis- og mannvirkjastofnun

Property registry and housing market data from Iceland's Housing and Construction Authority.

## Data Sources

### Kaupskrá fasteigna (Property Purchase Registry)

**URL:** `https://frs3o1zldvgn.objectstorage.eu-frankfurt-1.oci.customer-oci.com/n/frs3o1zldvgn/b/public_data_for_download/o/kaupskra.csv`

**Format:** CSV (semicolon delimited, ISO-8859-1 encoded)

**Update frequency:** Daily

**Coverage:** 2006-present, ~222k transactions

#### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| faerslunumer | int | Unique transaction ID |
| fastnum | str | Property number |
| heimilisfang | str | Address |
| postnr | int | Postal code |
| heinum | int | Location ID (7-digit, different from iceaddr hnitnum) |
| svfn | str | Municipality code |
| sveitarfelag | str | Municipality name |
| utgdag | date | Purchase agreement date |
| thinglystdags | timestamp | Registration date |
| kaupverd | int | Purchase price (**in thousands of ISK**) |
| fasteignamat | int | Property valuation at sale (thousands) |
| fasteignamat_gildandi | int | Current property valuation (thousands) |
| brunabotamat_gildandi | int | Fire insurance value (thousands) |
| byggar | int | Year built |
| einflm | float | Unit area (m²) |
| lod_flm | float | Lot area |
| fjherb | int | Number of rooms |
| tegund | str | Property type: Sérbýli, Fjölbýli, Sumarhús, Atvinnuhúsnæði, etc |
| fullbuid | bool | Whether property is complete |
| onothaefur_samningur | bool | Unusable for analysis (related party, multiple properties, etc) |

#### Caveats

- **Prices in thousands:** kaupverd=57000 means 57,000,000 ISK
- **heinum ≠ hnitnum:** Cannot join directly to iceaddr, use address+postnr instead
- **onothaefur_samningur:** Filter these for market analysis (related party sales, partial transfers)

## Geocoding with iceaddr

The `heinum` field does NOT match iceaddr's `hnitnum`. Join on parsed address components:

```sql
-- Parse address from kaupskra
TRIM(regexp_extract(HEIMILISFANG, '^([^0-9]+)', 1)) as street_name,
TRY_CAST(regexp_extract(HEIMILISFANG, '([0-9]+)', 1) AS INTEGER) as house_num,
upper(regexp_extract(HEIMILISFANG, '[0-9]+([a-zA-Z]?)$', 1)) as house_letter

-- Join to iceaddr.stadfong
ON lower(street_name) = lower(heiti_nf)
AND house_num = husnr
AND postnr = postnr
AND house_letter = COALESCE(upper(bokst), '')
```

**Match rate:** ~97%

## Processed Data

**Location:** `/data/processed/kaupskra_geocoded.parquet`

Includes all kaupskra fields plus:
- `lat`, `lng` - WGS84 coordinates from iceaddr
- `verd_per_m2` - Price per m² (in ISK, not thousands)

## Quick Queries

```bash
# Summary stats
duckdb -c "SELECT count(*), count(lat), median(kaupverd*1000/einflm_m2) FROM 'data/processed/kaupskra_geocoded.parquet' WHERE NOT onothaefur AND tegund='Fjölbýli'"

# Recent Reykjavík sales
duckdb -c "SELECT heimilisfang, kaupverd*1000 as kr, einflm_m2 FROM 'data/processed/kaupskra_geocoded.parquet' WHERE postnr BETWEEN 101 AND 128 AND kaupsamningur_dags >= '2024-01-01' ORDER BY kaupsamningur_dags DESC LIMIT 20"
```

## License

Open data, attribution required: "Byggir á upplýsingum frá Húsnæðis- og mannvirkjastofnun"

## Related

- [iceaddr](https://github.com/sveinbjornt/iceaddr) - Icelandic address geocoding
- [Kaupverðsjá](https://hms.is/gogn-og-maelabord/maelabordfasteignaskra/kaupverdsja) - HMS interactive price viewer

---
name: energy
description: Iceland energy authority — electricity generation, use, fuel sales, power plants and licences. Use for energy-system analysis.
---

# Energy — Umhverfis- og orkustofnun

**Requires:** Tier 0 (core).

The Energy Authority publishes downloadable numerical energy tables and a live
electricity-indicators dashboard. This source starts with the stable XLSX archive.

## Data

**Catalogue:** `https://orkustofnun.is/upplysingar/talnaefni/raforka`

`OS-2025-1-throun-raforkuframleidslu-a-islandi-1969-2024.xlsx` contains the
1969–2024 electricity-generation series by source. It also contains a
guarantees-of-origin table; that describes certificate attribution, not physical
generation.

## Usage

```bash
uv run python scripts/energy.py list
uv run python scripts/energy.py fetch
```

Writes `data/processed/energy_generation.parquet` in long form: `year`,
`series`, `gwh`.

## Caveats

1. Publication filenames and prefixes change (`OS`, `UOS`, `ROS`); discover new
   releases from the catalogue rather than assuming a future URL.
2. The newest catalogue link can temporarily 404 while the previous release
   remains live; retain a working-version fallback.
3. The source does not state a general reuse licence. Cite the Authority.

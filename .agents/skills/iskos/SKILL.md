---
name: iskos
description: Icelandic National Election Study (ÍSKOS) — voter surveys 1983–2021 via GAGNÍS/Harvard Dataverse. Party ID, left-right, trust, demographics.
---

# ÍSKOS — Íslenska Kosningarannsóknin (Icelandic National Election Study)

Voter survey data from every Icelandic parliamentary election 1983–2021.
Hosted on GAGNÍS (Harvard Dataverse) at gagnis.hi.is.

## API Endpoints

- **DDI metadata**: `GET gagnis.hi.is/api/access/datafile/{fileId}/metadata/ddi` — XML with variable names, labels, value labels
- **TSV download**: `GET gagnis.hi.is/api/access/datafile/{fileId}` — full dataset (~1.6 MB for 2021)

## Dataset Mapping

| Year | DOI | File ID |
|------|-----|---------|
| 2021 | 10.34881/0ERQOZ | 235 |
| 2017 | 10.34881/1.00011 | 201 |
| 2016 | 10.34881/1.00010 | 192 |
| 2013 | 10.34881/1.00009 | 178 |
| 2009 | 10.34881/1.00008 | 170 |
| 2007 | 10.34881/1.00007 | 165 |
| 2003 | 10.34881/1.00006 | 160 |
| 1999 | 10.34881/1.00005 | 150 |
| 1995 | 10.34881/1.00004 | 138 |
| 1991 | 10.34881/1.00003 | 131 |
| 1987 | 10.34881/1.00002 | 97 |
| 1983 | 10.34881/1.00001 | 119 |

Campaign surveys (access-restricted — 403 on data download):
- 2021: 10.34881/HVPGFX
- 2017: 10.34881/PZJCHA
- 2016: 10.34881/SZUY8A

## Key Variables

- **Party ID**: `pidsupport3` — 1=S, 2=B, 3=D, 4=V, 6=P, 8=C, 10=M, 11=F, 12=J
- **Party thermometer**: `prtfeel_S`, `prtfeel_D`, etc. (0-10 scale)
- **Left-right**: `lrscale` (0-10)
- **Trust**: `trustparl`, `trustgov`, `trustjud`, `trustmed`
- **Demographics**: `gender` (1=M, 2=F), `age`, `area` (1=capital, 2=rural), `elecdist`
- **Voting**: `vote21`, `prtvote21`
- **Weights**: `demweight` (demographic), `polweight` (political)

## ÍSKOS 2024 — Staða

Kosningar voru haldnar 30. nóvember 2024. Könnunin var framkvæmd en gögnin eru EKKI enn aðgengileg á GAGNÍS.

Á iskos.hi.is segir: "Gögnin verða gerð aðgengileg eftir að gagnaöflun og frágangi þeirra er lokið."

Rannsóknarhópurinn birti bráðabirgðaniðurstöður í Stjórnmál og stjórnsýsla (júní 2025).

### Hvenær er von á gögnum?

| Kosningar | Birting á GAGNÍS | Biðtími           |
|-----------|------------------|--------------------|
| Sep 2021  | Júní 2023        | ~21 mánuðir        |
| Okt 2017  | Jan 2021         | ~38 mán. (biðröð)  |

Miðað við 2021-fordæmið (~21 mánuðir) og kosningarnar 30. nóvember 2024:

**Áætluð birting: seint 2026 — fyrri hluta 2027**

### Rannsóknarhópur

- Eva H. Önnudóttir, Agnar Freyr Helgason, Hulda Thorisdottir, Jón Gunnar Ólafsson (verkefnisstjórar)
- Ólafur Þ. Harðarson (prófessor emeritus, stofnandi ÍSKOS 1983)
- Hafsteinn Einarsson (rannsakandi)
- Netfang: icenes@hi.is

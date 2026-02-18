---
title: Dansport ehf. - Fjárhagsgreining og verðmat
---

# Dansport ehf.

<Alert status="info">
Gögn úr ársreikningum 2021-2024 frá Ársreikningaskrá RSK.
</Alert>

```sql financials
SELECT * FROM skatturinn.dansport_financials
```

```sql valuation
SELECT * FROM skatturinn.dansport_valuation
```

```sql info
SELECT * FROM skatturinn.dansport_info
```

## Helstu upplýsingar

<Grid cols=3>
  <BigValue
    data={financials.filter(d => d.year === 2024)}
    value=revenue_m
    title="Tekjur 2024"
    fmt="#,##0 M ISK"
  />
  <BigValue
    data={financials.filter(d => d.year === 2024)}
    value=total_equity_m
    title="Eigið fé 2024"
    fmt="#,##0 M ISK"
  />
  <BigValue
    data={financials.filter(d => d.year === 2024)}
    value=equity_ratio
    title="Eiginfjárhlutfall"
    fmt="#,##0'%'"
  />
</Grid>

---

## Þróun tekna og hagnaðar

Tekjur hafa lækkað um 28% frá 2021. Félagið hefur tapað 2 af síðustu 3 árum.

<LineChart
  data={financials}
  x=year
  y={['revenue_m', 'total_equity_m']}
  yAxisTitle="Milljónir ISK"
  title="Tekjur og eigið fé"
/>

<BarChart
  data={financials}
  x=year
  y={['operating_profit_m', 'net_profit_m']}
  yAxisTitle="Milljónir ISK"
  title="Rekstrarhagnaður og hagnaður ársins"
/>

---

## Efnahagsreikningur

```sql balance_breakdown
SELECT
  year,
  total_assets_m,
  total_equity_m,
  short_term_debt_m,
  total_assets_m - total_equity_m - short_term_debt_m as other_m
FROM skatturinn.dansport_financials
```

<BarChart
  data={balance_breakdown}
  x=year
  y={['total_equity_m', 'short_term_debt_m']}
  yAxisTitle="Milljónir ISK"
  title="Eigið fé vs skuldir"
  type=stacked100
/>

---

## Lykilhlutföll

<LineChart
  data={financials}
  x=year
  y={['equity_ratio', 'gross_margin']}
  yAxisTitle="Prósent"
  title="Eiginfjárhlutfall og framlegð"
/>

<DataTable data={financials} rows=all>
  <Column id=year title="Ár" />
  <Column id=revenue_m title="Tekjur (M)" fmt="#,##0.0" />
  <Column id=operating_profit_m title="Rekstrarhagn. (M)" fmt="#,##0.0" />
  <Column id=net_profit_m title="Hagnaður (M)" fmt="#,##0.0" />
  <Column id=total_equity_m title="Eigið fé (M)" fmt="#,##0.0" />
  <Column id=equity_ratio title="EF hlutf. %" fmt="#,##0.0" />
  <Column id=employees title="Starfsmenn" />
</DataTable>

---

## Verðmat

Þrjár aðferðir notaðar til að meta virði félagsins:

<DataTable data={valuation} rows=all>
  <Column id=method title="Aðferð" />
  <Column id=low_m title="Lágt (M)" fmt="#,##0" />
  <Column id=mid_m title="Miðgildi (M)" fmt="#,##0" />
  <Column id=high_m title="Hátt (M)" fmt="#,##0" />
  <Column id=notes title="Athugasemdir" />
</DataTable>

```sql valuation_chart
SELECT
  method,
  low_m,
  mid_m,
  high_m
FROM skatturinn.dansport_valuation
```

<BarChart
  data={valuation_chart}
  x=method
  y={['low_m', 'mid_m', 'high_m']}
  yAxisTitle="Milljónir ISK"
  title="Verðmatssvið eftir aðferð"
  swapXY=true
/>

<Alert status="warning">
<b>Niðurstaða:</b> Sanngjörn verðáætlun er 150-180 milljónir ISK, sem samsvarar um 1x bókfærðu virði. Lækkandi tekjur og óstöðug afkoma réttlæta ekki hærra verðmat.
</Alert>

---

## Félagsupplýsingar

| Atriði | Gildi |
|--------|-------|
| **Nafn** | Dansport ehf. |
| **Kennitala** | 4807032350 |
| **Heimilisfang** | Smáratorg 1, 201 Kópavogur |
| **Starfsemi** | Smásala og heildverslun með íþróttafatnað |
| **Vörumerki** | Hummel, Saucony, Ronhill, Newline, ZIGZAG |
| **Verslanir** | Smáratorg, Miðhraun, Reykjanesbær, Vefverslun |
| **Eigendur** | Ævar Sveinsson (50%), Berglind Þóra Steinarsdóttir (50%) |
| **Starfsmenn** | 19 ársverk (2024) |
| **Stofnár** | 2003 |

---

## Áhættuþættir

1. **Lækkandi tekjur** - 28% lækkun frá 2021 til 2024
2. **Óstöðug afkoma** - Tap 2 af 4 síðustu árum
3. **Há leigugjöld** - ~70M ISK/ári, 418M skuldbinding til 2029
4. **Lágt handbært fé** - Aðeins 1M ISK í árslok 2024
5. **Samkeppni** - Erlend netverslun og keðjur

## Styrkir

1. **Sterkt eiginfjárhlutfall** - 52% er vel yfir viðmiðum
2. **Engar langtímaskuldir**
3. **Vörumerkjadreifing** - Sterk staða með Hummel o.fl.
4. **Reynslumikið eignarafl**

---

<LastRefreshed/>

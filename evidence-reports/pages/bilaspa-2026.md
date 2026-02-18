# Bílasöluspá 2026

Spálíkan fyrir íslenskan bílamarkað byggt á stefnubreytingum 1. janúar 2026 og tollastefnu.

```sql summary
SELECT * FROM bilaspa.summary
```

```sql fuel_forecast
SELECT * FROM bilaspa.forecast_by_fuel
```

```sql chinese_brands
SELECT * FROM bilaspa.chinese_brands
```

```sql scenarios
SELECT * FROM bilaspa.scenarios
```

```sql policy_impacts
SELECT * FROM bilaspa.policy_impacts
```

## Lykilniðurstöður

<BigValue
  data={summary.filter(d => d.metric === 'total_market_2026')}
  value="value"
  title="Spá nýskráninga 2026"
  fmt="num0"
/>

<BigValue
  data={summary.filter(d => d.metric === 'market_change_pct')}
  value="value"
  title="Breyting frá 2024"
  fmt="pct1"
  comparison="Samdráttur"
/>

<BigValue
  data={summary.filter(d => d.metric === 'ev_market_share_2026')}
  value="value"
  title="Hlutdeild rafbíla"
  fmt="pct1"
/>

<BigValue
  data={summary.filter(d => d.metric === 'chinese_ev_share_2026')}
  value="value"
  title="Kínverskir af rafbílum"
  fmt="pct1"
/>

---

## Forsendur spálíkans

### Stefnubreytingar 1. janúar 2026

| Breyting | Áhrif |
|----------|-------|
| Vörugjald rafbíla | 5% → 0% |
| Rafbílastyrkur | 900.000 → 500.000 kr. |
| Vörugjald tengiltvinna | 5% → **30%** |
| Vörugjald bensín/dísel | 5% → 15% (lágmark) |
| Kílómetragjald | Nýtt: 6,95 kr./km |

### Tollaforskot Íslands

Ísland er með **fríverslunarsamning við Kína** (0% tollar) en ESB hefur 27-45% tolla á kínverska rafbíla.

---

## Spá eftir orkugjafa

<BarChart
  data={fuel_forecast}
  x="fuel_type"
  y={["sales_2024", "sales_2026"]}
  title="Nýskráningar eftir orkugjafa"
  yAxisTitle="Fjöldi bíla"
/>

<DataTable data={fuel_forecast} rows=10>
  <Column id="fuel_type" title="Orkugjafi"/>
  <Column id="sales_2024" title="2024" fmt="num0"/>
  <Column id="sales_2026" title="2026 spá" fmt="num0"/>
  <Column id="change_pct" title="Breyting" fmt="pct1"/>
  <Column id="market_share_2026" title="Hlutdeild 2026" fmt="pct1"/>
</DataTable>

### Helstu atriði

- **Tengiltvinnbílar hrynja um 41%** vegna 6x hækkunar á vörugjöldum
- **Rafbílar halda velli** þrátt fyrir lægri styrk (-2,7%)
- **Bensín/dísel lækka** vegna hærri gjalda (-16 til -17%)

---

## Kínverskir rafbílar

Kínverskir rafbílar njóta verðforskots á Íslandi vegna tollaleysis.

<BarChart
  data={chinese_brands}
  x="brand"
  y="forecast_2026"
  title="Spá fyrir kínversk bílamerki 2026"
  yAxisTitle="Nýskráningar"
  swapXY=true
/>

<DataTable data={chinese_brands} rows=10>
  <Column id="brand" title="Merki"/>
  <Column id="forecast_2026" title="Spá 2026" fmt="num0"/>
  <Column id="eu_tariff_pct" title="ESB-tollur" fmt="pct0"/>
  <Column id="iceland_advantage" title="Forskot Íslands"/>
</DataTable>

### Af hverju vaxa kínverskir bílar?

1. **Engin verndartollur** - Ísland 0% vs ESB 27-45%
2. **Samkeppnishæft verð** - Lægra verð en evrópskir rafbílar
3. **Vörugjöld felld niður** - Rafbílar njóta 0% vörugjalds
4. **Nýir aðilar** - XPENG kom inn 2024, fleiri væntanlegir

---

## Sviðsmyndir

<DataTable data={scenarios} rows=5>
  <Column id="name" title="Sviðsmynd"/>
  <Column id="total_sales" title="Heildarsala" fmt="num0"/>
  <Column id="ev_share_pct" title="Rafbílahlutdeild" fmt="pct0"/>
  <Column id="chinese_ev_share_pct" title="Kínverskir af rafbílum" fmt="pct0"/>
  <Column id="description" title="Lýsing"/>
</DataTable>

---

## Áhrif stefnubreytinga

<BarChart
  data={policy_impacts}
  x="segment"
  y="demand_change_pct"
  title="Áætluð eftirspurnarbreyting eftir orkugjafa"
  yAxisTitle="Breyting (%)"
/>

<DataTable data={policy_impacts} rows=10>
  <Column id="segment" title="Orkugjafi"/>
  <Column id="price_change_pct" title="Verðbreyting %" fmt="pct1"/>
  <Column id="demand_elasticity" title="Verðteygni"/>
  <Column id="demand_change_pct" title="Eftirspurnarbreyting %" fmt="pct1"/>
</DataTable>

---

## Aðferðafræði

Spálíkanið byggir á:

1. **Grunnlínu 2024** - Áætlaðar nýskráningar eftir orkugjafa
2. **Stefnuáhrifum** - Verðbreytingar og verðteygni eftirspurnar
3. **Markaðsaðlögun** - 5% samdráttur í heildarmarkaði
4. **Kínverskt forskot** - 15% aukavöxtur vegna tollaleysis

### Takmarkanir

- Byggt á áætluðum tölum fyrir 2024
- Verðteygni er mat, ekki mæld
- Gerir ekki ráð fyrir nýjum aðilum á markaði
- Tekur ekki tillit til vaxtastigs eða efnahagsþróunar

---

*Síðast uppfært: janúar 2026*

*Gögn: Samgöngustofa, Skatturinn, ESB-tollaupplýsingar*

"""Build tax-burden.html - modernized version of Efling's 2019 report."""

import csv
import json
from pathlib import Path


def csv_to_json(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8").lstrip("\ufeff")
    reader = csv.DictReader(text.strip().splitlines())
    return list(reader)


def main():
    d = Path("data/processed")

    datasets = {
        "TAX_BURDEN": csv_to_json(d / "tax_burden.csv"),
        "INCOME_BY_SOURCE": csv_to_json(d / "income_by_source.csv"),
        "INCOME_GENDER": csv_to_json(d / "income_by_source_gender.csv"),
        "TOTAL_DIST": csv_to_json(d / "total_income_distribution.csv"),
        "EMPLOY_DIST": csv_to_json(d / "employment_income_distribution.csv"),
        "INCOME_AGE": csv_to_json(d / "income_by_age.csv"),
    }

    data_js = "\n".join(
        f"const {name} = {json.dumps(data, ensure_ascii=False)};"
        for name, data in datasets.items()
    )

    html = TEMPLATE.replace("/* __DATA__ */", data_js)
    Path("tax-burden.html").write_text(html, encoding="utf-8")
    print(f"Built tax-burden.html ({len(html) / 1024:.0f} KB)")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="is">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Skattbyrði og tekjudreifing — uppfært 2024</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:#f9fafb;color:#1f2937;line-height:1.6;max-width:960px;margin:0 auto;padding:24px 16px}
  h1{font-size:1.7rem;margin-bottom:4px}
  .subtitle{color:#6b7280;margin-bottom:24px;font-size:.95rem}
  .tldr{background:#fff3e0;border-left:4px solid #e65100;padding:16px 20px;border-radius:0 12px 12px 0;margin-bottom:28px}
  .tldr strong{color:#bf360c}
  .card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin-bottom:20px}
  .card h3{font-size:1.05rem;margin-bottom:12px}
  .chart-wrap{position:relative;height:360px}
  .chart-wrap.tall{height:420px}
  .chart-wrap.xtall{height:480px}
  .metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}
  .metric{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px;text-align:center}
  .metric .value{font-size:1.5rem;font-weight:700}
  .metric .label{font-size:.8rem;color:#6b7280;margin-top:2px}
  .metric .delta{font-size:.85rem;margin-top:4px}
  .delta.red{color:#dc2626}
  .delta.green{color:#059669}
  .delta.orange{color:#d97706}
  .note{font-size:.85rem;color:#6b7280;margin-top:8px;font-style:italic}
  .context{background:#f3f4f6;border-radius:8px;padding:14px 18px;margin:12px 0;font-size:.9rem}
  .context strong{color:#374151}
  h2{font-size:1.25rem;margin:36px 0 16px;color:#1e293b;border-bottom:2px solid #e5e7eb;padding-bottom:8px}
  .sources{margin-top:40px;padding-top:20px;border-top:1px solid #e5e7eb;font-size:.82rem;color:#9ca3af}
  .sources a{color:#6b7280}
</style>
</head>
<body>

<h1>Sanngjörn dreifing skattbyrðar</h1>
<p class="subtitle">Uppfært með gögnum til 2024 &mdash; byggt á skýrslu Eflingar (Stefán Ólafsson & Indriði H. Þorláksson, 2019)</p>

<div class="tldr" id="tldr"></div>
<div class="metrics" id="key-metrics"></div>

<h2>I. Virkt skatthlutfall eftir aldri</h2>

<div class="card">
  <h3>Virkt skatthlutfall eftir aldurshópum, 1993 vs 2015 vs 2024</h3>
  <p class="note">Skattar á greiðslugrunni sem % af meðal heildartekjum. Sýnir hvernig skattbyrðin hefur þróast frá upphaflegu Efling-skýrslunni.</p>
  <div class="chart-wrap tall"><canvas id="chart-tax-rate-age"></canvas></div>
</div>

<div class="card">
  <h3>Þróun virks skatthlutfalls yfir tíma (25–54 ára)</h3>
  <p class="note">Meðaltal og miðgildi. Lægra hlutfall = lægri skattbyrði sem hlutfall af tekjum.</p>
  <div class="chart-wrap"><canvas id="chart-tax-rate-time"></canvas></div>
</div>

<h2>II. Tekjusamsetning og ójöfnuður</h2>

<div class="card">
  <h3>Fjármagnstekjur sem hlutfall af heildartekjum eftir aldri (2024)</h3>
  <p class="note">Eldri og hátekjuhópar hafa hlutfallslega meiri fjármagnstekjur &mdash; sem bera lægri skatt en launatekjur.</p>
  <div class="chart-wrap tall"><canvas id="chart-cap-share-age"></canvas></div>
</div>

<div class="card">
  <h3>Hlutfall fjármagnstekna af heildartekjum yfir tíma (25–54 ára)</h3>
  <p class="note">Fjármagnstekjur hafa aukist hlutfallslega frá hruni 2008.</p>
  <div class="chart-wrap"><canvas id="chart-cap-share-time"></canvas></div>
</div>

<div class="card">
  <h3>Dreifing: Heildartekjur vs. atvinnutekjur (2024, 25–54 ára)</h3>
  <p class="note">Bilið á milli línanna sýnir áhrif fjármagnstekna — mest efst í dreifingunni.</p>
  <div class="chart-wrap tall"><canvas id="chart-percentile"></canvas></div>
</div>

<div class="card">
  <h3>P90/P10 ójöfnuður yfir tíma (25–54 ára)</h3>
  <p class="note">Hærra hlutfall = meiri ójöfnuður. Rautt = heildartekjur, blátt = aðeins atvinnutekjur.</p>
  <div class="chart-wrap"><canvas id="chart-p90p10"></canvas></div>
</div>

<h2>III. Meðaltal vs. miðgildi</h2>

<div class="card">
  <h3>Meðaltal vs. miðgildi heildartekna (25–54 ára)</h3>
  <p class="note">Vaxandi bil sýnir aukinn ójöfnuð &mdash; fáir með mjög háar tekjur draga meðaltalið upp.</p>
  <div class="chart-wrap"><canvas id="chart-mean-median"></canvas></div>
</div>

<div class="card">
  <h3>Kynjamunur á heildartekjum (25–54 ára)</h3>
  <p class="note">Karlar hafa enn hærri heildartekjur, að hluta vegna meiri fjármagnstekna.</p>
  <div class="chart-wrap"><canvas id="chart-gender"></canvas></div>
</div>

<h2>IV. Tekjur og skattar eftir aldri (2024)</h2>

<div class="card">
  <h3>Tekjusamsetning eftir aldri (meðaltal á mánuði, 2024)</h3>
  <p class="note">Staflaður: atvinnutekjur + fjármagnstekjur + aðrar tekjur</p>
  <div class="chart-wrap tall"><canvas id="chart-income-age"></canvas></div>
</div>

<div class="card">
  <h3>Virkt skatthlutfall vs. hlutfall fjármagnstekna eftir aldri (2024)</h3>
  <p class="note">Sýnir hvernig hópar með hærra hlutfall fjármagnstekna greiða hlutfallslega lægri skatt.</p>
  <div class="chart-wrap tall"><canvas id="chart-tax-vs-cap"></canvas></div>
</div>

<div class="sources">
  <p><strong>Heimildir:</strong></p>
  <p>Hagstofa Íslands, tafla <a href="https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__3_tekjur__1_tekjur_skattframtol/TEK01001.px">TEK01001</a> — Tekjur eftir kyni og aldri 1990–2024</p>
  <p>Hagstofa Íslands, tafla <a href="https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__3_tekjur__1_tekjur_skattframtol/TEK01006.px">TEK01006</a> — Dreifing heildartekna 1990–2024</p>
  <p>Hagstofa Íslands, tafla <a href="https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__3_tekjur__1_tekjur_skattframtol/TEK01007.px">TEK01007</a> — Dreifing atvinnutekna 1990–2024</p>
  <p style="margin-top:8px;">Byggt á: <a href="https://www.efling.is/wp-content/uploads/2021/08/Sanngjo%CC%88rn-dreIfing-skattbyrdar-lokaproof_A.pdf">Sanngjörn dreifing skattbyrðar</a> (Stefán Ólafsson & Indriði H. Þorláksson, febrúar 2019)</p>
  <p>Allar upphæðir í þúsundum króna á ári nema þar sem tekið er fram (mánaðartölur = deilt með 12).</p>
</div>

<script>
/* __DATA__ */

// ===== HELPERS =====
function val(row, y) { const v = parseFloat(row[String(y)]); return isNaN(v) ? null : v; }
function monthly(row, y) { const v = val(row, y); return v === null ? null : Math.round(v / 12); }

const years = []; for (let y=1990;y<=2024;y++) years.push(y);
const recentYears = years.filter(y => y >= 2000);

const red='#dc2626', blue='#2563eb', green='#059669', orange='#d97706', purple='#7c3aed', gray='#9ca3af';
Chart.defaults.font.family = "-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif";
Chart.defaults.font.size = 12;

// ===== FIND ROWS =====
function findRow(data, filters) {
  return data.find(r => Object.entries(filters).every(([k,v]) => r[k]?.includes(v)));
}
function findRows(data, filters) {
  return data.filter(r => Object.entries(filters).every(([k,v]) => r[k]?.includes(v)));
}

// Tax burden data
const tbMean = TAX_BURDEN.filter(r => r['Eining']?.includes('altal'));
const tbMedian = TAX_BURDEN.filter(r => r['Eining']?.includes('gildi'));

// Age groups for charts
const ageKeys = ['16 - 19','20 - 24','25 - 29','30 - 34','35 - 39','40 - 44','45 - 49','50 - 54','55 - 59','60 - 64','65 - 69','70 - 74','75 - 79'];
const ageLabels = ageKeys.map(a => a.replace(/ /g,'').replace('-','–'));

function getByAge(type, stat, y) {
  const rows = stat === 'mean' ? tbMean : tbMedian;
  return ageKeys.map(age => {
    const row = rows.find(r => r['Tekjur og skattar']?.includes(type) && r['Aldur']?.includes(age));
    return row ? val(row, y) : null;
  });
}

// Effective tax rate by age
function taxRate(y) {
  return ageKeys.map(age => {
    const total = tbMean.find(r => r['Tekjur og skattar']?.includes('Heildartekjur') && r['Aldur']?.includes(age));
    const tax = tbMean.find(r => r['Tekjur og skattar']?.includes('Skattar') && r['Aldur']?.includes(age));
    if (!total || !tax) return null;
    const t = val(total, y), s = val(tax, y);
    return t > 0 && s !== null ? Math.round(s / t * 1000) / 10 : null;
  });
}

// Key metrics (25-54, mean)
const total2554 = findRow(tbMean, {'Tekjur og skattar':'Heildartekjur','Aldur':'25 - 54'});
const tax2554 = findRow(tbMean, {'Tekjur og skattar':'Skattar','Aldur':'25 - 54'});
const cap2554 = findRow(tbMean, {'Tekjur og skattar':'rmagnstekjur','Aldur':'25 - 54'});
const disp2554 = findRow(tbMean, {'Tekjur og skattar':'funartekjur','Aldur':'25 - 54'});
const totalMed2554 = findRow(tbMedian, {'Tekjur og skattar':'Heildartekjur','Aldur':'25 - 54'});

const taxRate2024 = val(tax2554, 2024) / val(total2554, 2024) * 100;
const taxRate1993 = val(tax2554, 1993) / val(total2554, 1993) * 100;
const taxRate2015 = val(tax2554, 2015) / val(total2554, 2015) * 100;
const capShare2024 = val(cap2554, 2024) / val(total2554, 2024) * 100;
const mean2024m = monthly(total2554, 2024);
const med2024m = monthly(totalMed2554, 2024);
const meanMedianGap = Math.round((mean2024m / med2024m - 1) * 100);

document.getElementById('tldr').innerHTML = `
  <strong>Efling-skýrslan 2019</strong> sýndi hvernig skattbyrði færðist frá hátekjufólki til lágtekjufólks á árunum 1993–2015.
  Uppfærð gögn til 2024 sýna að þróunin hefur <strong>haldið áfram</strong>: virkt skatthlutfall 25–54 ára
  var ${taxRate1993.toFixed(1)}% árið 1993, hækkaði í ${taxRate2015.toFixed(1)}% árið 2015, og er nú
  <strong>${taxRate2024.toFixed(1)}%</strong> árið 2024. Á sama tíma hafa fjármagnstekjur — sem bera lægri skatt —
  vaxið og eru nú <strong>${capShare2024.toFixed(0)}%</strong> af heildartekjum þessa aldurshóps.
`;

document.getElementById('key-metrics').innerHTML = `
  <div class="metric">
    <div class="value">${taxRate2024.toFixed(1)}%</div>
    <div class="label">Virkt skatthlutfall 2024</div>
    <div class="delta orange">25–54 ára, meðaltal</div>
  </div>
  <div class="metric">
    <div class="value">${capShare2024.toFixed(0)}%</div>
    <div class="label">Hlutfall fjármagnstekna</div>
    <div class="delta red">af meðal heildartekjum</div>
  </div>
  <div class="metric">
    <div class="value">${mean2024m} þ.kr.</div>
    <div class="label">Meðal heildartekjur/mán.</div>
    <div class="delta">25–54 ára, 2024</div>
  </div>
  <div class="metric">
    <div class="value">${med2024m} þ.kr.</div>
    <div class="label">Miðgildi/mán.</div>
    <div class="delta red">Meðaltal ${meanMedianGap}% hærra</div>
  </div>
`;

// ===== CHART 1: Tax rate by age, 1993 vs 2015 vs 2024 =====
new Chart(document.getElementById('chart-tax-rate-age'), {
  type: 'bar',
  data: {
    labels: ageLabels,
    datasets: [
      { label: '1993', data: taxRate(1993), backgroundColor: 'rgba(37,99,235,0.6)', borderColor: blue, borderWidth: 1 },
      { label: '2015', data: taxRate(2015), backgroundColor: 'rgba(217,119,6,0.6)', borderColor: orange, borderWidth: 1 },
      { label: '2024', data: taxRate(2024), backgroundColor: 'rgba(220,38,38,0.6)', borderColor: red, borderWidth: 1 },
    ],
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}%` }}},
    scales: {
      x: { grid: { display: false }},
      y: { title: { display: true, text: 'Virkt skatthlutfall (%)' }, ticks: { callback: v => v + '%' }},
    },
  },
});

// ===== CHART 2: Tax rate over time (25-54) =====
function taxRateTimeSeries(totalRow, taxRow) {
  return recentYears.map(y => {
    const t = val(totalRow, y), s = val(taxRow, y);
    return t > 0 && s !== null ? Math.round(s / t * 1000) / 10 : null;
  });
}

new Chart(document.getElementById('chart-tax-rate-time'), {
  type: 'line',
  data: {
    labels: recentYears,
    datasets: [
      {
        label: 'Virkt skatthlutfall (meðaltal)',
        data: taxRateTimeSeries(total2554, tax2554),
        borderColor: red, borderWidth: 2.5, tension: 0.3, pointRadius: 2,
      },
    ],
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { tooltip: { callbacks: { label: ctx => `${ctx.parsed.y}%` }}},
    scales: {
      x: { grid: { display: false }},
      y: { title: { display: true, text: '% af heildartekjum' }, ticks: { callback: v => v + '%' }},
    },
  },
});

// ===== CHART 3: Capital share by age 2024 =====
function capShareByAge(y) {
  return ageKeys.map(age => {
    const total = tbMean.find(r => r['Tekjur og skattar']?.includes('Heildartekjur') && r['Aldur']?.includes(age));
    const cap = tbMean.find(r => r['Tekjur og skattar']?.includes('rmagnstekjur') && r['Aldur']?.includes(age));
    if (!total || !cap) return null;
    const t = val(total, y), c = val(cap, y);
    return t > 0 ? Math.round(c / t * 1000) / 10 : null;
  });
}

new Chart(document.getElementById('chart-cap-share-age'), {
  type: 'bar',
  data: {
    labels: ageLabels,
    datasets: [
      { label: 'Hlutfall fjármagnstekna (%)', data: capShareByAge(2024), backgroundColor: 'rgba(220,38,38,0.7)', borderColor: red, borderWidth: 1 },
    ],
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { tooltip: { callbacks: { label: ctx => `${ctx.parsed.y}%` }}},
    scales: {
      x: { grid: { display: false }},
      y: { title: { display: true, text: '% af heildartekjum' }, ticks: { callback: v => v + '%' }},
    },
  },
});

// ===== CHART 4: Capital share time series =====
const src2554mean = INCOME_BY_SOURCE.filter(r => r['Aldur']?.includes('25 - 54') && r['Eining']?.includes('altal'));
const totalIncTS = src2554mean.find(r => r['Tekjur og skattar']?.includes('Heildartekjur'));
const capIncTS = src2554mean.find(r => r['Tekjur og skattar']?.includes('rmagnstekjur'));

new Chart(document.getElementById('chart-cap-share-time'), {
  type: 'line',
  data: {
    labels: recentYears,
    datasets: [{
      label: 'Hlutfall fjármagnstekna',
      data: recentYears.map(y => {
        const t = val(totalIncTS, y), c = val(capIncTS, y);
        return t && c ? Math.round(c / t * 1000) / 10 : null;
      }),
      borderColor: red, backgroundColor: 'rgba(220,38,38,0.1)',
      borderWidth: 2.5, fill: true, tension: 0.3, pointRadius: 2,
    }],
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { tooltip: { callbacks: { label: ctx => `${ctx.parsed.y}%` }}},
    scales: {
      x: { grid: { display: false }},
      y: { title: { display: true, text: '% af heildartekjum' }, ticks: { callback: v => v + '%' }},
    },
  },
});

// ===== CHART 5: Percentile comparison =====
const pctLabels = ['P10','P20','P30','P40','P50','P60','P70','P80','P90','P95','P99'];
const pctCodes = ['10%','20%','30%','40%','50%','60%','70%','80%','90%','95%','99%'];
const totalDist2554 = TOTAL_DIST.filter(r => r['Aldur']?.includes('25 - 54'));
const employDist2554 = EMPLOY_DIST.filter(r => r['Aldur']?.includes('25 - 54'));

function getPctData(rows, y) {
  return pctCodes.map(code => {
    const row = rows.find(r => r['Eining'] === code);
    return row ? monthly(row, y) : null;
  });
}

const totalPct2024 = getPctData(totalDist2554, 2024);
const emplPct2024 = getPctData(employDist2554, 2024);

// Compute gap at each percentile
const pctGap = totalPct2024.map((t, i) => t && emplPct2024[i] ? t - emplPct2024[i] : null);

new Chart(document.getElementById('chart-percentile'), {
  type: 'line',
  data: {
    labels: pctLabels,
    datasets: [
      { label: 'Heildartekjur', data: totalPct2024, borderColor: red, borderWidth: 2.5, tension: 0.3, pointRadius: 4, pointBackgroundColor: red },
      { label: 'Atvinnutekjur', data: emplPct2024, borderColor: blue, borderWidth: 2.5, tension: 0.3, pointRadius: 4, pointBackgroundColor: blue },
      { label: 'Munur (fjármagn+annað)', data: pctGap, borderColor: orange, borderWidth: 1.5, borderDash: [5,3], tension: 0.3, pointRadius: 3 },
    ],
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y} þ.kr./mán.` }}},
    scales: {
      x: { grid: { display: false }},
      y: { title: { display: true, text: 'þús. kr./mánuði' }},
    },
  },
});

// ===== CHART 6: P90/P10 =====
function getP90P10(rows, y) {
  const p90 = rows.find(r => r['Eining'] === '90%');
  const p10 = rows.find(r => r['Eining'] === '10%');
  if (!p90 || !p10) return null;
  const v90 = val(p90, y), v10 = val(p10, y);
  return v90 && v10 ? Math.round(v90 / v10 * 100) / 100 : null;
}

new Chart(document.getElementById('chart-p90p10'), {
  type: 'line',
  data: {
    labels: recentYears,
    datasets: [
      { label: 'Heildartekjur P90/P10', data: recentYears.map(y => getP90P10(totalDist2554, y)), borderColor: red, borderWidth: 2.5, tension: 0.3, pointRadius: 2 },
      { label: 'Atvinnutekjur P90/P10', data: recentYears.map(y => getP90P10(employDist2554, y)), borderColor: blue, borderWidth: 2.5, tension: 0.3, pointRadius: 2 },
    ],
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}x` }}},
    scales: {
      x: { grid: { display: false }},
      y: { title: { display: true, text: 'P90/P10 hlutfall' }},
    },
  },
});

// ===== CHART 7: Mean vs Median =====
new Chart(document.getElementById('chart-mean-median'), {
  type: 'line',
  data: {
    labels: recentYears,
    datasets: [
      { label: 'Meðaltal', data: recentYears.map(y => monthly(total2554, y)), borderColor: red, borderWidth: 2.5, tension: 0.3, pointRadius: 2 },
      { label: 'Miðgildi', data: recentYears.map(y => monthly(totalMed2554, y)), borderColor: blue, borderWidth: 2.5, tension: 0.3, pointRadius: 2 },
    ],
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y} þ.kr./mán.` }}},
    scales: { x: { grid: { display: false }}, y: { title: { display: true, text: 'þús. kr./mánuði' }}},
  },
});

// ===== CHART 8: Gender gap =====
const genderMean = INCOME_GENDER.filter(r => r['Tekjur og skattar']?.includes('Heildartekjur') && r['Eining']?.includes('altal'));
const maleInc = genderMean.find(r => r['Kyn']?.includes('Karlar'));
const femaleInc = genderMean.find(r => r['Kyn']?.includes('Konur'));

new Chart(document.getElementById('chart-gender'), {
  type: 'line',
  data: {
    labels: recentYears,
    datasets: [
      { label: 'Karlar', data: recentYears.map(y => monthly(maleInc, y)), borderColor: blue, borderWidth: 2.5, tension: 0.3, pointRadius: 2 },
      { label: 'Konur', data: recentYears.map(y => monthly(femaleInc, y)), borderColor: purple, borderWidth: 2.5, tension: 0.3, pointRadius: 2 },
    ],
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y} þ.kr./mán.` }}},
    scales: { x: { grid: { display: false }}, y: { title: { display: true, text: 'þús. kr./mánuði' }}},
  },
});

// ===== CHART 9: Income by age stacked =====
function ageVal(type, y) {
  return ageKeys.map(age => {
    const row = INCOME_AGE.find(r => r['Tekjur og skattar']?.includes(type) && r['Aldur']?.includes(age) && r['Eining']?.includes('altal'));
    return row ? monthly(row, y) : null;
  });
}

new Chart(document.getElementById('chart-income-age'), {
  type: 'bar',
  data: {
    labels: ageLabels,
    datasets: [
      { label: 'Atvinnutekjur', data: ageVal('Atvinnutekjur', 2024), backgroundColor: blue },
      { label: 'Fjármagnstekjur', data: ageVal('rmagnstekjur', 2024), backgroundColor: red },
      { label: 'Aðrar tekjur', data: ageVal('rar tekjur', 2024), backgroundColor: gray },
    ],
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y} þ.kr./mán.` }}},
    scales: { x: { stacked: true, grid: { display: false }}, y: { stacked: true, title: { display: true, text: 'þús. kr./mánuði' }}},
  },
});

// ===== CHART 10: Tax rate vs capital share scatter by age =====
const taxRates2024 = taxRate(2024);
const capShares2024 = capShareByAge(2024);

new Chart(document.getElementById('chart-tax-vs-cap'), {
  type: 'scatter',
  data: {
    datasets: [{
      label: 'Aldurshópar 2024',
      data: ageKeys.map((age, i) => ({
        x: capShares2024[i], y: taxRates2024[i], label: ageLabels[i]
      })).filter(d => d.x !== null && d.y !== null),
      backgroundColor: 'rgba(220,38,38,0.7)',
      borderColor: red, borderWidth: 1, pointRadius: 7,
    }],
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      tooltip: {
        callbacks: {
          label: ctx => `${ctx.raw.label}: fjármagn ${ctx.raw.x}%, skattur ${ctx.raw.y}%`
        }
      },
    },
    scales: {
      x: { title: { display: true, text: 'Hlutfall fjármagnstekna (%)' }, ticks: { callback: v => v + '%' }},
      y: { title: { display: true, text: 'Virkt skatthlutfall (%)' }, ticks: { callback: v => v + '%' }},
    },
  },
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()

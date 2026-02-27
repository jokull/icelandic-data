"""Build income-distribution.html with embedded data from CSVs."""

import csv
import json
from pathlib import Path


def csv_to_json(path: Path) -> list[dict]:
    """Read CSV and return list of dicts."""
    text = path.read_text(encoding="utf-8")
    # Strip any BOM
    text = text.lstrip("\ufeff")
    reader = csv.DictReader(text.strip().splitlines())
    return list(reader)


def main():
    data_dir = Path("data/processed")

    datasets = {
        "INCOME_BY_SOURCE_DATA": csv_to_json(data_dir / "income_by_source.csv"),
        "INCOME_BY_SOURCE_GENDER_DATA": csv_to_json(data_dir / "income_by_source_gender.csv"),
        "INCOME_BY_AGE_DATA": csv_to_json(data_dir / "income_by_age.csv"),
        "TOTAL_DIST_DATA": csv_to_json(data_dir / "total_income_distribution.csv"),
        "EMPLOY_DIST_DATA": csv_to_json(data_dir / "employment_income_distribution.csv"),
    }

    # Verify encoding
    sample = datasets["INCOME_BY_SOURCE_DATA"][0]
    assert "Meðaltal" in str(sample.values()) or "Heildartekjur" in str(sample.values()), \
        f"Encoding issue! Sample: {sample}"
    print(f"  Sample row keys: {list(sample.keys())[:3]}")

    data_js = "\n".join(
        f"const {name} = {json.dumps(data, ensure_ascii=False)};"
        for name, data in datasets.items()
    )

    html = TEMPLATE.replace("/* __DATA_PLACEHOLDER__ */", data_js)

    Path("income-distribution.html").write_text(html, encoding="utf-8")
    print(f"Built income-distribution.html ({len(html) / 1024:.0f} KB)")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="is">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tekjudreifing á Íslandi — Laun vs. heildartekjur</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: #f9fafb; color: #1f2937; line-height: 1.6;
    max-width: 960px; margin: 0 auto; padding: 24px 16px;
  }
  h1 { font-size: 1.7rem; margin-bottom: 4px; }
  .subtitle { color: #6b7280; margin-bottom: 24px; font-size: 0.95rem; }
  .tldr {
    background: #eff6ff; border-left: 4px solid #2563eb;
    padding: 16px 20px; border-radius: 0 12px 12px 0; margin-bottom: 28px;
  }
  .tldr strong { color: #1e40af; }
  .card {
    background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
    padding: 20px; margin-bottom: 20px;
  }
  .card h3 { font-size: 1.05rem; margin-bottom: 12px; }
  .chart-wrap { position: relative; height: 360px; }
  .chart-wrap.tall { height: 420px; }
  .metrics {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px; margin-bottom: 20px;
  }
  .metric {
    background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
    padding: 16px; text-align: center;
  }
  .metric .value { font-size: 1.6rem; font-weight: 700; }
  .metric .label { font-size: 0.8rem; color: #6b7280; margin-top: 2px; }
  .metric .delta { font-size: 0.85rem; margin-top: 4px; }
  .delta.red { color: #dc2626; }
  .note { font-size: 0.85rem; color: #6b7280; margin-top: 8px; font-style: italic; }
  .sources {
    margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb;
    font-size: 0.82rem; color: #9ca3af;
  }
  .sources a { color: #6b7280; }
</style>
</head>
<body>

<h1>Tekjudreifing á Íslandi</h1>
<p class="subtitle">Laun eru aðeins hluti myndarinnar &mdash; fjármagnstekjur auka ójöfnuð</p>

<div class="tldr" id="tldr"></div>

<div class="metrics" id="key-metrics"></div>

<div class="card">
  <h3>Tekjusamsetning yfir tíma (25–54 ára, meðaltal á mánuði)</h3>
  <p class="note">Atvinnutekjur, fjármagnstekjur og aðrar tekjur — í þús. kr./mán.</p>
  <div class="chart-wrap tall"><canvas id="chart-composition"></canvas></div>
</div>

<div class="card">
  <h3>Fjármagnstekjur sem hlutfall af heildartekjum</h3>
  <p class="note">Hlutfall fjármagnstekna af meðal heildartekjum, 25–54 ára</p>
  <div class="chart-wrap"><canvas id="chart-capital-share"></canvas></div>
</div>

<div class="card">
  <h3>Dreifing heildartekna vs. atvinnutekna (2024, 25–54 ára)</h3>
  <p class="note">Hundraðshlutar — munurinn á milli línanna sýnir áhrif fjármagnstekna</p>
  <div class="chart-wrap tall"><canvas id="chart-percentile-compare"></canvas></div>
</div>

<div class="card">
  <h3>P90/P10 hlutfall — ójöfnuður yfir tíma</h3>
  <p class="note">Hærra hlutfall = meiri ójöfnuður. Heildartekjur (rautt) vs. atvinnutekjur (blátt).</p>
  <div class="chart-wrap"><canvas id="chart-p90p10"></canvas></div>
</div>

<div class="card">
  <h3>Meðaltal vs. miðgildi heildartekna (25–54 ára)</h3>
  <p class="note">Þegar meðaltal er miklu hærra en miðgildi þýðir það skekkta dreifingu — fáir með mjög háar tekjur draga meðaltal upp.</p>
  <div class="chart-wrap"><canvas id="chart-mean-median"></canvas></div>
</div>

<div class="card">
  <h3>Kynjamunur á heildartekjum (25–54 ára, meðaltal)</h3>
  <p class="note">Þús. kr. á mánuði</p>
  <div class="chart-wrap"><canvas id="chart-gender"></canvas></div>
</div>

<div class="card">
  <h3>Tekjur eftir aldri 2024 (meðaltal á mánuði)</h3>
  <p class="note">Brotið niður í atvinnutekjur, fjármagnstekjur og aðrar tekjur</p>
  <div class="chart-wrap tall"><canvas id="chart-age"></canvas></div>
</div>

<div class="sources">
  <p><strong>Heimildir:</strong></p>
  <p>Hagstofa Íslands, tafla <a href="https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__3_tekjur__1_tekjur_skattframtol/TEK01001.px">TEK01001</a> — Tekjur eftir kyni og aldri 1990–2024</p>
  <p>Hagstofa Íslands, tafla <a href="https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__3_tekjur__1_tekjur_skattframtol/TEK01006.px">TEK01006</a> — Dreifing heildartekna 1990–2024</p>
  <p>Hagstofa Íslands, tafla <a href="https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__3_tekjur__1_tekjur_skattframtol/TEK01007.px">TEK01007</a> — Dreifing atvinnutekna 1990–2024</p>
  <p style="margin-top:8px;">Tekjur af skattframtölum. Upphæðir í þúsundum króna á ári, sýndar sem mánaðartölur (deilt með 12).</p>
</div>

<script>
/* __DATA_PLACEHOLDER__ */

// ===== HELPERS =====
function val(row, year) {
  const v = parseFloat(row[String(year)]);
  return isNaN(v) ? null : v;
}
function monthly(row, year) {
  const v = val(row, year);
  return v === null ? null : Math.round(v / 12);
}

const years = [];
for (let y = 1990; y <= 2024; y++) years.push(y);
const recentYears = years.filter(y => y >= 2000);

// Colors
const blue = '#2563eb', red = '#dc2626', green = '#059669';
const orange = '#d97706', purple = '#7c3aed', gray = '#9ca3af';

Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif";
Chart.defaults.font.size = 12;

// ===== FIND ROWS =====
// Income by source (25-54, all genders)
const src25_54_mean = INCOME_BY_SOURCE_DATA.filter(r =>
  r['Aldur']?.includes('25 - 54') && r['Eining']?.includes('altal')
);
const src25_54_median = INCOME_BY_SOURCE_DATA.filter(r =>
  r['Aldur']?.includes('25 - 54') && r['Eining']?.includes('gildi')
);

const totalInc = src25_54_mean.find(r => r['Tekjur og skattar']?.includes('Heildartekjur'));
const emplInc = src25_54_mean.find(r => r['Tekjur og skattar']?.includes('Atvinnutekjur'));
const capInc = src25_54_mean.find(r => r['Tekjur og skattar']?.includes('rmagnstekjur'));
const otherInc = src25_54_mean.find(r => r['Tekjur og skattar']?.includes('rar tekjur'));
const totalIncMedian = src25_54_median.find(r => r['Tekjur og skattar']?.includes('Heildartekjur'));

// ===== KEY METRICS =====
const mean2024 = monthly(totalInc, 2024);
const median2024 = monthly(totalIncMedian, 2024);
const cap2024 = monthly(capInc, 2024);
const empl2024 = monthly(emplInc, 2024);
const capShare2024 = Math.round(val(capInc, 2024) / val(totalInc, 2024) * 100);
const meanMedianGap = Math.round((mean2024 / median2024 - 1) * 100);

document.getElementById('tldr').innerHTML = `
  <strong>TL;DR:</strong> Meðallaun vanmeta raunverulegan tekjumun. Þegar fjármagnstekjur eru teknar með hækkar
  bilið á milli ríkustu og fátækustu verulega. Árið 2024 voru meðal heildartekjur 25–54 ára <strong>${mean2024} þús. kr./mán.</strong>
  en miðgildi aðeins <strong>${median2024} þús.</strong> — munurinn (${meanMedianGap}%) stafar að mestu af fjármagnstekjum
  sem renna til efstu hópanna.
`;

document.getElementById('key-metrics').innerHTML = `
  <div class="metric">
    <div class="value">${mean2024} þ.kr.</div>
    <div class="label">Meðal heildartekjur/mán.</div>
    <div class="delta">25–54 ára, 2024</div>
  </div>
  <div class="metric">
    <div class="value">${median2024} þ.kr.</div>
    <div class="label">Miðgildi heildartekna/mán.</div>
    <div class="delta red">Meðaltal ${meanMedianGap}% hærra</div>
  </div>
  <div class="metric">
    <div class="value">${cap2024} þ.kr.</div>
    <div class="label">Fjármagnstekjur/mán.</div>
    <div class="delta red">${capShare2024}% af heildartekjum</div>
  </div>
  <div class="metric">
    <div class="value">${empl2024} þ.kr.</div>
    <div class="label">Atvinnutekjur/mán.</div>
    <div class="delta">Meðaltal, 25–54 ára</div>
  </div>
`;

// ===== 1. STACKED: Income composition =====
new Chart(document.getElementById('chart-composition'), {
  type: 'line',
  data: {
    labels: recentYears,
    datasets: [
      {
        label: 'Atvinnutekjur', data: recentYears.map(y => monthly(emplInc, y)),
        backgroundColor: 'rgba(37,99,235,0.3)', borderColor: blue, borderWidth: 2, fill: true, tension: 0.3,
      },
      {
        label: 'Fjármagnstekjur', data: recentYears.map(y => monthly(capInc, y)),
        backgroundColor: 'rgba(220,38,38,0.3)', borderColor: red, borderWidth: 2, fill: true, tension: 0.3,
      },
      {
        label: 'Aðrar tekjur', data: recentYears.map(y => monthly(otherInc, y)),
        backgroundColor: 'rgba(156,163,175,0.3)', borderColor: gray, borderWidth: 2, fill: true, tension: 0.3,
      },
    ],
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y} þ.kr./mán.` }}},
    scales: {
      x: { grid: { display: false }},
      y: { stacked: true, title: { display: true, text: 'þús. kr./mánuði' }},
    },
  },
});

// ===== 2. Capital share =====
new Chart(document.getElementById('chart-capital-share'), {
  type: 'line',
  data: {
    labels: recentYears,
    datasets: [{
      label: 'Hlutfall fjármagnstekna',
      data: recentYears.map(y => {
        const t = val(totalInc, y), c = val(capInc, y);
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

// ===== 3. Percentile comparison =====
const pctLabels = ['P10','P20','P30','P40','P50','P60','P70','P80','P90','P95','P99'];
const pctCodes = ['10%','20%','30%','40%','50%','60%','70%','80%','90%','95%','99%'];

const totalDist2554 = TOTAL_DIST_DATA.filter(r => r['Aldur']?.includes('25 - 54'));
const employDist2554 = EMPLOY_DIST_DATA.filter(r => r['Aldur']?.includes('25 - 54'));

function getPctData(rows, year) {
  return pctCodes.map(code => {
    const row = rows.find(r => r['Eining'] === code);
    return row ? monthly(row, year) : null;
  });
}

new Chart(document.getElementById('chart-percentile-compare'), {
  type: 'line',
  data: {
    labels: pctLabels,
    datasets: [
      {
        label: 'Heildartekjur 2024', data: getPctData(totalDist2554, 2024),
        borderColor: red, borderWidth: 2.5, tension: 0.3, pointRadius: 4, pointBackgroundColor: red,
      },
      {
        label: 'Atvinnutekjur 2024', data: getPctData(employDist2554, 2024),
        borderColor: blue, borderWidth: 2.5, tension: 0.3, pointRadius: 4, pointBackgroundColor: blue,
      },
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

// ===== 4. P90/P10 ratio =====
function getP90P10(rows, year) {
  const p90 = rows.find(r => r['Eining'] === '90%');
  const p10 = rows.find(r => r['Eining'] === '10%');
  if (!p90 || !p10) return null;
  const v90 = val(p90, year), v10 = val(p10, year);
  return v90 && v10 ? Math.round(v90 / v10 * 100) / 100 : null;
}

new Chart(document.getElementById('chart-p90p10'), {
  type: 'line',
  data: {
    labels: recentYears,
    datasets: [
      {
        label: 'Heildartekjur P90/P10', data: recentYears.map(y => getP90P10(totalDist2554, y)),
        borderColor: red, borderWidth: 2.5, tension: 0.3, pointRadius: 2,
      },
      {
        label: 'Atvinnutekjur P90/P10', data: recentYears.map(y => getP90P10(employDist2554, y)),
        borderColor: blue, borderWidth: 2.5, tension: 0.3, pointRadius: 2,
      },
    ],
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}x` }}},
    scales: {
      x: { grid: { display: false }},
      y: { title: { display: true, text: 'Hlutfall P90/P10' }},
    },
  },
});

// ===== 5. Mean vs Median =====
new Chart(document.getElementById('chart-mean-median'), {
  type: 'line',
  data: {
    labels: recentYears,
    datasets: [
      {
        label: 'Meðaltal', data: recentYears.map(y => monthly(totalInc, y)),
        borderColor: red, borderWidth: 2.5, tension: 0.3, pointRadius: 2,
      },
      {
        label: 'Miðgildi', data: recentYears.map(y => monthly(totalIncMedian, y)),
        borderColor: blue, borderWidth: 2.5, tension: 0.3, pointRadius: 2,
      },
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

// ===== 6. Gender gap =====
const genderMean = INCOME_BY_SOURCE_GENDER_DATA.filter(r =>
  r['Tekjur og skattar']?.includes('Heildartekjur') && r['Eining']?.includes('altal')
);
const maleInc = genderMean.find(r => r['Kyn']?.includes('Karlar'));
const femaleInc = genderMean.find(r => r['Kyn']?.includes('Konur'));

new Chart(document.getElementById('chart-gender'), {
  type: 'line',
  data: {
    labels: recentYears,
    datasets: [
      {
        label: 'Karlar', data: recentYears.map(y => monthly(maleInc, y)),
        borderColor: blue, borderWidth: 2.5, tension: 0.3, pointRadius: 2,
      },
      {
        label: 'Konur', data: recentYears.map(y => monthly(femaleInc, y)),
        borderColor: purple, borderWidth: 2.5, tension: 0.3, pointRadius: 2,
      },
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

// ===== 7. Income by age 2024 =====
const ageLabels = ['16-19','20-24','25-29','30-34','35-39','40-44','45-49','50-54','55-59','60-64','65-69','70-74','75-79'];
const ageLabelMap = {
  '16-19':'16 - 19','20-24':'20 - 24','25-29':'25 - 29','30-34':'30 - 34',
  '35-39':'35 - 39','40-44':'40 - 44','45-49':'45 - 49','50-54':'50 - 54',
  '55-59':'55 - 59','60-64':'60 - 64','65-69':'65 - 69','70-74':'70 - 74','75-79':'75 - 79',
};
const ageMean = INCOME_BY_AGE_DATA.filter(r => r['Eining']?.includes('altal'));
function ageRow(type) { return ageMean.filter(r => r['Tekjur og skattar']?.includes(type)); }
const ageEmpl = ageRow('Atvinnutekjur');
const ageCap = ageRow('rmagnstekjur');
const ageOther = ageRow('rar tekjur');

function ageVal(rows, ageKey) {
  const row = rows.find(r => r['Aldur']?.includes(ageLabelMap[ageKey]));
  return row ? monthly(row, 2024) : null;
}

new Chart(document.getElementById('chart-age'), {
  type: 'bar',
  data: {
    labels: ageLabels.map(a => a + ' ára'),
    datasets: [
      { label: 'Atvinnutekjur', data: ageLabels.map(a => ageVal(ageEmpl, a)), backgroundColor: blue },
      { label: 'Fjármagnstekjur', data: ageLabels.map(a => ageVal(ageCap, a)), backgroundColor: red },
      { label: 'Aðrar tekjur', data: ageLabels.map(a => ageVal(ageOther, a)), backgroundColor: gray },
    ],
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y} þ.kr./mán.` }}},
    scales: {
      x: { stacked: true, grid: { display: false }},
      y: { stacked: true, title: { display: true, text: 'þús. kr./mánuði' }},
    },
  },
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()

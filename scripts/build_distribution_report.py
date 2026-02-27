"""Build income-distribution.html - focused on total vs wage distribution comparison."""

import csv
import json
from pathlib import Path

import httpx


def csv_to_json(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8").lstrip("\ufeff")
    reader = csv.DictReader(text.strip().splitlines())
    return list(reader)


def fetch_gini():
    """Fetch Gini coefficient from EU-SILC."""
    r = httpx.post(
        "https://px.hagstofa.is/pxis/api/v1/is/Samfelag/launogtekjur/3_tekjur/2_tekjur_silc/LIF01110.px",
        json={"query": [], "response": {"format": "csv"}},
        timeout=30,
    )
    r.raise_for_status()
    text = r.content.decode("latin-1")
    Path("data/processed/gini.csv").write_text(text, encoding="utf-8")
    print("  Saved data/processed/gini.csv")
    return text


def main():
    d = Path("data/processed")

    # Fetch Gini if not cached
    if not (d / "gini.csv").exists():
        fetch_gini()

    datasets = {
        "INCOME_BY_SOURCE": csv_to_json(d / "income_by_source.csv"),
        "INCOME_GENDER": csv_to_json(d / "income_by_source_gender.csv"),
        "TOTAL_DIST": csv_to_json(d / "total_income_distribution.csv"),
        "EMPLOY_DIST": csv_to_json(d / "employment_income_distribution.csv"),
        "TAX_BURDEN": csv_to_json(d / "tax_burden.csv"),
        "GINI": csv_to_json(d / "gini.csv"),
    }

    data_js = "\n".join(
        f"const {name} = {json.dumps(data, ensure_ascii=False)};"
        for name, data in datasets.items()
    )

    html = TEMPLATE.replace("/* __DATA__ */", data_js)
    Path("income-distribution.html").write_text(html, encoding="utf-8")
    print(f"Built income-distribution.html ({len(html) / 1024:.0f} KB)")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="is">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tekjudreifing á Íslandi — Laun vs. heildartekjur 2024</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:#f9fafb;color:#1f2937;line-height:1.6;max-width:960px;margin:0 auto;padding:24px 16px}
  h1{font-size:1.7rem;margin-bottom:4px}
  .subtitle{color:#6b7280;margin-bottom:24px;font-size:.95rem}
  h2{font-size:1.25rem;margin:36px 0 16px;color:#1e293b;border-bottom:2px solid #e5e7eb;padding-bottom:8px}
  .tldr{background:#eff6ff;border-left:4px solid #2563eb;padding:16px 20px;border-radius:0 12px 12px 0;margin-bottom:28px}
  .tldr strong{color:#1e40af}
  .card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin-bottom:20px}
  .card h3{font-size:1.05rem;margin-bottom:12px}
  .chart-wrap{position:relative;height:360px}
  .chart-wrap.tall{height:440px}
  .chart-wrap.xtall{height:500px}
  .metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}
  .metric{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px;text-align:center}
  .metric .value{font-size:1.5rem;font-weight:700}
  .metric .label{font-size:.8rem;color:#6b7280;margin-top:2px}
  .metric .delta{font-size:.85rem;margin-top:4px}
  .delta.red{color:#dc2626}
  .delta.green{color:#059669}
  .note{font-size:.85rem;color:#6b7280;margin-top:8px;font-style:italic}
  .callout{background:#fef3c7;border-left:4px solid #d97706;padding:12px 16px;border-radius:0 8px 8px 0;margin:16px 0;font-size:.9rem}
  .callout strong{color:#92400e}
  .sources{margin-top:40px;padding-top:20px;border-top:1px solid #e5e7eb;font-size:.82rem;color:#9ca3af}
  .sources a{color:#6b7280}
</style>
</head>
<body>

<h1>Tekjudreifing á Íslandi 2024</h1>
<p class="subtitle">Heildartekjur &mdash; ekki bara laun &mdash; sýna raunverulegan ójöfnuð</p>

<div class="tldr" id="tldr"></div>
<div class="metrics" id="key-metrics"></div>

<h2>Dreifing heildartekna á Íslandi 2024</h2>

<div class="card" style="padding:24px">
  <h3 style="font-size:1.15rem;margin-bottom:2px">Dreifing heildartekna 25–54 ára, 2024</h3>
  <p style="color:#6b7280;font-size:.9rem;margin-bottom:16px">Þúsundir króna á mánuði — laun + fjármagnstekjur + aðrar tekjur</p>
  <div class="chart-wrap xtall"><canvas id="chart-histogram"></canvas></div>
  <p class="note" style="margin-top:12px">Metið út frá hundraðshlutamörkum (P10–P99) skattframtala. Samanburður: Hagstofa sýnir laun fullvinnandi með topp á 700–800 þ.kr./mán.</p>
</div>

<div class="callout">
  <strong>Samanburður við launadreifingu Hagstofunnar:</strong> Hagstofa birtir dreifingu <em>launa</em> fullvinnandi starfsfólks með meðaltal 845 þ.kr./mán. og topp á 700–800 þ.kr. Þegar fjármagnstekjur og aðrar tekjur bætast við (myndin hér) hækkar meðaltalið og halinn til hægri verður þyngri — þ.e. fleiri fá mjög háar tekjur.
</div>

<h2>Dreifing eftir hundraðshlutum</h2>

<div class="card">
  <h3>Heildartekjur eftir hundraðshlutum, staflaðar eftir tegund (25–54 ára, 2024)</h3>
  <p class="note">Hver stöpull sýnir mánaðartekjur á viðkomandi hundraðshluta. Rauði hlutinn (fjármagnstekjur + annað) stækkar verulega efst í dreifingunni.</p>
  <div class="chart-wrap xtall"><canvas id="chart-stacked-pct"></canvas></div>
</div>

<div class="card">
  <h3>Munur á heildartekjum og atvinnutekjum eftir hundraðshlutum (2024)</h3>
  <p class="note">Sýnir hversu mikið fjármagnstekjur og aðrar tekjur bæta við á hverjum stað í dreifingunni. P99 fær ~345 þ.kr./mán. umfram atvinnutekjur — P10 fær nánast ekkert.</p>
  <div class="chart-wrap tall"><canvas id="chart-gap"></canvas></div>
</div>

<div class="card">
  <h3>Hlutfall fjármagnstekna af heildartekjum eftir hundraðshlutum (nálgun)</h3>
  <p class="note">Reiknað sem munur heildartekna og atvinnutekna sem hlutfall af heildartekjum. Efstu hóparnir fá hlutfallslega miklu meiri tekjur utan launa.</p>
  <div class="chart-wrap tall"><canvas id="chart-nonwage-share"></canvas></div>
</div>

<h2>Þróun yfir tíma</h2>

<div class="card">
  <h3>Tekjusamsetning 25–54 ára yfir tíma (meðaltal á mánuði)</h3>
  <p class="note">Staflaður: atvinnutekjur, fjármagnstekjur og aðrar tekjur</p>
  <div class="chart-wrap tall"><canvas id="chart-composition"></canvas></div>
</div>

<div class="card">
  <h3>P90/P10 hlutfall: Heildartekjur vs. atvinnutekjur (25–54 ára)</h3>
  <p class="note">Hærra gildi = meiri ójöfnuður. Rautt (heildartekjur) er alltaf hærra en blátt (aðeins atvinnutekjur) — fjármagnstekjur auka ójöfnuð.</p>
  <div class="chart-wrap"><canvas id="chart-p90p10"></canvas></div>
</div>

<div class="card">
  <h3>Meðaltal vs. miðgildi heildartekna (25–54 ára)</h3>
  <p class="note">Vaxandi bil = skekkari dreifing. Fáir með háar tekjur draga meðaltalið upp.</p>
  <div class="chart-wrap"><canvas id="chart-mean-median"></canvas></div>
</div>

<div class="card">
  <h3>Gini-stuðull ráðstöfunartekna (EU-SILC)</h3>
  <p class="note">0 = fullkominn jöfnuður, 100 = fullkominn ójöfnuður. Brotið lína = án félagslegrar aðstoðar.</p>
  <div class="chart-wrap"><canvas id="chart-gini"></canvas></div>
</div>

<h2>Kynjamunur</h2>

<div class="card">
  <h3>Heildartekjur karla vs. kvenna (25–54 ára, meðaltal á mánuði)</h3>
  <div class="chart-wrap"><canvas id="chart-gender"></canvas></div>
</div>

<h2>Skattaívilnun fjármagnstekna</h2>

<div class="card" style="background:#fff8f0;border-left:4px solid #e65100">
  <h3>Kostnaður skattaívilnunar fjármagnstekna (Stefán Ólafsson, 2025)</h3>
  <p style="font-size:.92rem;margin-bottom:16px">
    Stefán Ólafsson, prófessor emeritus við HÍ og sérfræðingur Eflingar, benti á eftirfarandi
    í grein á <a href="https://efling.is/en/2025/08/tax-privileges-of-the-highest-earners/" style="color:#1e40af">Heimildinni</a> (ágúst 2025):
  </p>
  <div class="metrics" style="margin-bottom:16px">
    <div class="metric" style="border-color:#fed7aa">
      <div class="value" style="color:#dc2626">22%</div>
      <div class="label">Fjármagnstekjuskattur</div>
      <div class="delta">Flatur — óháð upphæð</div>
    </div>
    <div class="metric" style="border-color:#fed7aa">
      <div class="value" style="color:#2563eb">32–46%</div>
      <div class="label">Tekjuskattur á laun</div>
      <div class="delta">Þrjú þrep, stígandi</div>
    </div>
    <div class="metric" style="border-color:#fed7aa">
      <div class="value" style="color:#059669">+52 ma.kr.</div>
      <div class="label">Ef fjármagn skattlagt við 38%</div>
      <div class="delta">Viðbótartekjur ríkisins</div>
    </div>
    <div class="metric" style="border-color:#fed7aa">
      <div class="value" style="color:#d97706">~27 ma.kr.</div>
      <div class="label">Barnabætur + húsnæðisstuðn.</div>
      <div class="delta">Helmingi minna en ívilnunin</div>
    </div>
  </div>
  <div style="font-size:.9rem;line-height:1.7">
    <p><strong>Lykilniðurstöður:</strong></p>
    <ul style="margin:8px 0 0 20px">
      <li>Tekjur ríkisins af fjármagnstekjuskatti 2023: <strong>73 ma.kr.</strong></li>
      <li>Ef skattlagðar eins og laun (38%): <strong>125 ma.kr.</strong> — aukning um <strong>52 ma.kr.</strong></li>
      <li>Ef skattlagðar við efsta þrep (46%): <strong>152 ma.kr.</strong> — aukning um <strong>79 ma.kr.</strong></li>
      <li>Ríkið greiðir ~14,8 ma.kr. í barnabætur og ~12 ma.kr. í húsnæðisstuðning — <strong>samtals ~27 ma.kr.</strong></li>
      <li>Skattaívilnun fjármagnstekna kostar þannig <strong>tvöfalt meira</strong> en þessi velferðarkerfi samanlagt.</li>
      <li>Meira en <strong>2/3 allra fjármagnstekna</strong> renna til efstu þriðjungs tekjuhópa.</li>
      <li>Fyrir 1997 voru fjármagnstekjur skattlagðar svipað og laun.</li>
    </ul>
    <p style="margin-top:12px;color:#6b7280;font-size:.85rem">
      Launamaður með 472 þ.kr./mán. greiðir ~10 prósentustigum hærri skatt en sá sem fær sömu upphæð sem fjármagnstekjur.
    </p>
  </div>
</div>

<div class="callout" style="border-left-color:#dc2626;background:#fef2f2">
  <strong>Samhengi við gröfin hér að ofan:</strong> Grafið á P99 sýnir að efsta 1% fær ~345 þ.kr./mán. í fjármagnstekjur
  og aðrar tekjur umfram atvinnutekjur. Þessar tekjur eru skattlagðar við 22% í stað 32–46%.
  Þetta er kjarni þess ójafnaðar sem skýrslan sýnir: ekki bara að efstu hóparnir fá meiri tekjur,
  heldur greiða þeir líka <em>lægra hlutfall</em> af þeim í skatt.
</div>

<div class="sources">
  <p><strong>Heimildir:</strong></p>
  <p>Hagstofa Íslands — <a href="https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__3_tekjur__1_tekjur_skattframtol/TEK01001.px">TEK01001</a> (tekjur eftir kyni/aldri),
  <a href="https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__3_tekjur__1_tekjur_skattframtol/TEK01006.px">TEK01006</a> (dreifing heildartekna),
  <a href="https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__3_tekjur__1_tekjur_skattframtol/TEK01007.px">TEK01007</a> (dreifing atvinnutekna),
  <a href="https://px.hagstofa.is/pxis/pxweb/is/Samfelag/Samfelag__launogtekjur__3_tekjur__2_tekjur_silc/LIF01110.px">LIF01110</a> (Gini-stuðull)</p>
  <p>Tekjur af skattframtölum. Mánaðartölur = árstekjur / 12.</p>
  <p style="margin-top:8px;">Sjá einnig: <a href="https://hagstofa.is/utgafur/frettasafn/laun-og-tekjur/laun-2024/">Laun 2024</a> (Hagstofa) og
  <a href="https://efling.is/en/2025/08/tax-privileges-of-the-highest-earners/">Skattaívilnanir hátekjufólks</a> (Stefán Ólafsson, 2025)</p>
</div>

<script>
/* __DATA__ */

function val(r,y){const v=parseFloat(r[String(y)]);return isNaN(v)?null:v}
function monthly(r,y){const v=val(r,y);return v===null?null:Math.round(v/12)}

const years=[];for(let y=1990;y<=2024;y++)years.push(y);
const recentYears=years.filter(y=>y>=2000);

const red='#dc2626',blue='#2563eb',green='#059669',orange='#d97706',purple='#7c3aed',gray='#9ca3af';
Chart.defaults.font.family="-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif";
Chart.defaults.font.size=12;

// ===== DATA PREP =====
const pctLabels=['P10','P20','P30','P40','P50','P60','P70','P80','P90','P95','P99'];
const pctCodes=['10%','20%','30%','40%','50%','60%','70%','80%','90%','95%','99%'];

const totalDist2554=TOTAL_DIST.filter(r=>r['Aldur']?.includes('25 - 54'));
const employDist2554=EMPLOY_DIST.filter(r=>r['Aldur']?.includes('25 - 54'));

function getPct(rows,y){
  return pctCodes.map(c=>{const r=rows.find(r=>r['Eining']===c);return r?monthly(r,y):null});
}

const totalPct=getPct(totalDist2554,2024);
const emplPct=getPct(employDist2554,2024);
const gap=totalPct.map((t,i)=>t&&emplPct[i]?t-emplPct[i]:null);

// Income by source (25-54)
const src2554mean=INCOME_BY_SOURCE.filter(r=>r['Aldur']?.includes('25 - 54')&&r['Eining']?.includes('altal'));
const src2554med=INCOME_BY_SOURCE.filter(r=>r['Aldur']?.includes('25 - 54')&&r['Eining']?.includes('gildi'));
const totalInc=src2554mean.find(r=>r['Tekjur og skattar']?.includes('Heildartekjur'));
const emplInc=src2554mean.find(r=>r['Tekjur og skattar']?.includes('Atvinnutekjur'));
const capInc=src2554mean.find(r=>r['Tekjur og skattar']?.includes('rmagnstekjur'));
const otherInc=src2554mean.find(r=>r['Tekjur og skattar']?.includes('rar tekjur'));
const totalMed=src2554med.find(r=>r['Tekjur og skattar']?.includes('Heildartekjur'));

// Key numbers
const mean2024=monthly(totalInc,2024);
const med2024=monthly(totalMed,2024);
const emplMean2024=monthly(emplInc,2024);
const capMean2024=monthly(capInc,2024);
const capShare=Math.round(val(capInc,2024)/val(totalInc,2024)*100);
const meanMedGap=Math.round((mean2024/med2024-1)*100);
const p99total=totalPct[10]; // P99
const p99empl=emplPct[10];
const p10total=totalPct[0];
const p10empl=emplPct[0];

document.getElementById('tldr').innerHTML=`
  <strong>TL;DR:</strong> Hagstofan sýnir dreifingu <em>launa</em> með meðaltal 845 þ.kr./mán. En þegar fjármagnstekjur og
  aðrar tekjur eru teknar inn hækkar meðaltalið í <strong>${mean2024} þ.kr./mán.</strong> — aukning um ~${mean2024-845} þ.kr.
  Miðgildið hækkar mun minna (í ${med2024} þ.kr.) sem þýðir að aukningin rennur til fárra.
  Á P99 (efsta 1%) bæta fjármagnstekjur við <strong>${gap[10]} þ.kr./mán.</strong> en á P10 aðeins <strong>${gap[0]} þ.kr.</strong>
`;

document.getElementById('key-metrics').innerHTML=`
  <div class="metric"><div class="value">${mean2024} þ.kr.</div><div class="label">Meðal heildartekjur/mán.</div><div class="delta">25–54 ára</div></div>
  <div class="metric"><div class="value">845 þ.kr.</div><div class="label">Meðal laun/mán.</div><div class="delta">(Hagstofa, fullvinnandi)</div></div>
  <div class="metric"><div class="value">+${mean2024-845} þ.kr.</div><div class="label">Munur á heild vs. laun</div><div class="delta red">Rennur mest til efstu hópa</div></div>
  <div class="metric"><div class="value">${capShare}%</div><div class="label">Fjármagnstekjur af heildinni</div><div class="delta red">Skattlagðar við 22%</div></div>
`;

// ===== HISTOGRAM: Piecewise-uniform density from percentile CDF =====
// Between each pair of known percentiles, we assume uniform density.
// This is mathematically exact: e.g. 10% of population lies between P10 and P20.

function buildSegments(pctValues) {
  // pctValues[0..10] = monthly income at P10,P20,P30,P40,P50,P60,P70,P80,P90,P95,P99
  // Returns array of {lo, hi, mass} where mass is fraction of population
  const fracs = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.99];
  const segs = [];
  // 0% to 10%: from 0 to P10
  segs.push({lo: 0, hi: pctValues[0], mass: 0.10});
  // Between consecutive percentiles
  for (let i = 0; i < fracs.length - 1; i++) {
    segs.push({lo: pctValues[i], hi: pctValues[i+1], mass: fracs[i+1] - fracs[i]});
  }
  // Above P99: 1% from P99 to ~P99*1.8 (rough upper tail)
  segs.push({lo: pctValues[10], hi: pctValues[10] * 1.8, mass: 0.01});
  return segs;
}

function histogramFromSegments(segs, binEdges) {
  // For each histogram bin, sum up contributions from each segment
  const bins = new Array(binEdges.length - 1).fill(0);
  for (const seg of segs) {
    if (seg.hi <= seg.lo) continue;
    const density = seg.mass / (seg.hi - seg.lo); // mass per unit income
    for (let b = 0; b < bins.length; b++) {
      const bLo = binEdges[b], bHi = binEdges[b + 1];
      // Overlap between segment [seg.lo, seg.hi] and bin [bLo, bHi]
      const overlapLo = Math.max(seg.lo, bLo);
      const overlapHi = Math.min(seg.hi, bHi);
      if (overlapHi > overlapLo) {
        bins[b] += density * (overlapHi - overlapLo) * 100; // as percentage
      }
    }
  }
  return bins;
}

// Bin edges matching Hagstofa exactly: <500, then 50k intervals to >1.700
const binEdges = [0, 500];
for (let v = 550; v <= 1700; v += 50) binEdges.push(v);
binEdges.push(5500); // last bin catches >1.700

function fmtK(n) {
  if (n >= 1000) return (n/1000|0) + '.' + String(n%1000).padStart(3,'0');
  return String(n);
}
const simpleLabels = binEdges.slice(0, -1).map((v, i) => {
  if (i === 0) return '<500';
  if (i === binEdges.length - 2) return '>1.700';
  return fmtK(v) + '-' + fmtK(binEdges[i+1]);
});

const totalSegs = buildSegments(totalPct);
const totalHist = histogramFromSegments(totalSegs, binEdges);

// Median and mean positions (bin index)
const medBinIdx = binEdges.findIndex((e, i) => i > 0 && totalPct[4] < e) - 1;
const meanBinIdx = binEdges.findIndex((e, i) => i > 0 && mean2024 < e) - 1;
// Wage mean (845) bin index for comparison
const wageMeanBinIdx = binEdges.findIndex((e, i) => i > 0 && 845 < e) - 1;

// Hagstofa teal color
const teal = '#0d9488';

// Mean/median annotation plugin — staggered labels to avoid overlap
const annotationPlugin = {
  id: 'verticalLines',
  afterDraw(chart) {
    const ctx = chart.ctx;
    const xAxis = chart.scales.x;
    const yAxis = chart.scales.y;
    const barW = (xAxis.getPixelForValue(1) - xAxis.getPixelForValue(0)) / 2;

    const lines = [
      {idx: medBinIdx,      label: 'Miðgildi ' + totalPct[4] + ' þ.kr.',  color: '#1e40af', dash: null,   yOff: 0},
      {idx: wageMeanBinIdx, label: 'Meðal laun 845 þ.kr.',                color: '#6b7280', dash: [3,3],  yOff: 16},
      {idx: meanBinIdx,     label: 'Meðaltal ' + mean2024 + ' þ.kr.',     color: '#dc2626', dash: [6,4],  yOff: 32},
    ];

    for (const l of lines) {
      if (l.idx < 0) continue;
      const x = xAxis.getPixelForValue(l.idx) + barW;
      const labelY = yAxis.top + 14 + l.yOff;
      ctx.save();
      ctx.beginPath();
      ctx.strokeStyle = l.color;
      ctx.lineWidth = 2;
      if (l.dash) ctx.setLineDash(l.dash);
      ctx.moveTo(x, yAxis.top);
      ctx.lineTo(x, yAxis.bottom);
      ctx.stroke();
      // Label with background
      ctx.font = 'bold 11px -apple-system,system-ui,sans-serif';
      const tw = ctx.measureText(l.label).width;
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.fillRect(x - tw/2 - 3, labelY - 11, tw + 6, 15);
      ctx.fillStyle = l.color;
      ctx.textAlign = 'center';
      ctx.fillText(l.label, x, labelY);
      ctx.restore();
    }
  }
};

new Chart(document.getElementById('chart-histogram'), {
  type: 'bar',
  data: {
    labels: simpleLabels,
    datasets: [{
      label: 'Heildartekjur',
      data: totalHist,
      backgroundColor: teal + 'cc',
      borderColor: teal,
      borderWidth: 1,
      barPercentage: 1,
      categoryPercentage: 1,
    }],
  },
  plugins: [annotationPlugin],
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: {display: false},
      tooltip: {callbacks: {label: ctx => `${ctx.parsed.y.toFixed(1)}%`}},
    },
    scales: {
      x: {
        grid: {display: false},
        title: {display: true, text: 'Þúsundir króna á mánuði'},
        ticks: {maxRotation: 60, autoSkip: true, maxTicksLimit: 25},
      },
      y: {
        title: {display: true, text: '% framteljenda'},
        ticks: {callback: v => v.toFixed(0) + '%'},
        beginAtZero: true,
      },
    },
  },
});

// ===== CHART 1: Stacked percentile bars =====
new Chart(document.getElementById('chart-stacked-pct'),{
  type:'bar',
  data:{
    labels:pctLabels,
    datasets:[
      {label:'Atvinnutekjur',data:emplPct,backgroundColor:blue},
      {label:'Fjármagnstekjur + annað',data:gap,backgroundColor:red},
    ],
  },
  options:{
    responsive:true,maintainAspectRatio:false,
    plugins:{
      tooltip:{callbacks:{
        label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y} þ.kr./mán.`,
        footer:items=>{const t=items.reduce((s,i)=>s+i.parsed.y,0);return `Heild: ${t} þ.kr./mán.`}
      }},
    },
    scales:{
      x:{stacked:true,grid:{display:false},title:{display:true,text:'Hundraðshluti tekjudreifingarinnar'}},
      y:{stacked:true,title:{display:true,text:'þús. kr./mánuði'}},
    },
  },
});

// ===== CHART 2: Gap chart =====
new Chart(document.getElementById('chart-gap'),{
  type:'bar',
  data:{
    labels:pctLabels,
    datasets:[{
      label:'Tekjur umfram atvinnutekjur',data:gap,
      backgroundColor:pctLabels.map((_,i)=>i>=8?'rgba(220,38,38,0.8)':i>=5?'rgba(217,119,6,0.6)':'rgba(156,163,175,0.5)'),
      borderColor:pctLabels.map((_,i)=>i>=8?red:i>=5?orange:gray),
      borderWidth:1,
    }],
  },
  options:{
    responsive:true,maintainAspectRatio:false,
    plugins:{tooltip:{callbacks:{label:ctx=>`+${ctx.parsed.y} þ.kr./mán.`}}},
    scales:{
      x:{grid:{display:false},title:{display:true,text:'Hundraðshluti'}},
      y:{title:{display:true,text:'þús. kr./mánuði umfram atvinnutekjur'}},
    },
  },
});

// ===== CHART 3: Non-wage share by percentile =====
const nonWageShare=totalPct.map((t,i)=>t&&emplPct[i]?Math.round((t-emplPct[i])/t*1000)/10:null);

new Chart(document.getElementById('chart-nonwage-share'),{
  type:'bar',
  data:{
    labels:pctLabels,
    datasets:[{
      label:'Hlutfall tekna utan launa',data:nonWageShare,
      backgroundColor:pctLabels.map((_,i)=>i>=8?'rgba(220,38,38,0.8)':i>=5?'rgba(217,119,6,0.6)':'rgba(37,99,235,0.5)'),
      borderWidth:1,
    }],
  },
  options:{
    responsive:true,maintainAspectRatio:false,
    plugins:{tooltip:{callbacks:{label:ctx=>`${ctx.parsed.y}%`}}},
    scales:{
      x:{grid:{display:false},title:{display:true,text:'Hundraðshluti'}},
      y:{title:{display:true,text:'% af heildartekjum'},ticks:{callback:v=>v+'%'}},
    },
  },
});

// ===== CHART 4: Stacked composition over time =====
new Chart(document.getElementById('chart-composition'),{
  type:'line',
  data:{
    labels:recentYears,
    datasets:[
      {label:'Atvinnutekjur',data:recentYears.map(y=>monthly(emplInc,y)),backgroundColor:'rgba(37,99,235,0.3)',borderColor:blue,borderWidth:2,fill:true,tension:.3},
      {label:'Fjármagnstekjur',data:recentYears.map(y=>monthly(capInc,y)),backgroundColor:'rgba(220,38,38,0.3)',borderColor:red,borderWidth:2,fill:true,tension:.3},
      {label:'Aðrar tekjur',data:recentYears.map(y=>monthly(otherInc,y)),backgroundColor:'rgba(156,163,175,0.3)',borderColor:gray,borderWidth:2,fill:true,tension:.3},
    ],
  },
  options:{
    responsive:true,maintainAspectRatio:false,
    plugins:{tooltip:{callbacks:{label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y} þ.kr./mán.`}}},
    scales:{x:{grid:{display:false}},y:{stacked:true,title:{display:true,text:'þús. kr./mánuði'}}},
  },
});

// ===== CHART 5: P90/P10 =====
function getP90P10(rows,y){
  const p90=rows.find(r=>r['Eining']==='90%'),p10=rows.find(r=>r['Eining']==='10%');
  if(!p90||!p10)return null;
  const v90=val(p90,y),v10=val(p10,y);
  return v90&&v10?Math.round(v90/v10*100)/100:null;
}

new Chart(document.getElementById('chart-p90p10'),{
  type:'line',
  data:{
    labels:recentYears,
    datasets:[
      {label:'Heildartekjur P90/P10',data:recentYears.map(y=>getP90P10(totalDist2554,y)),borderColor:red,borderWidth:2.5,tension:.3,pointRadius:2},
      {label:'Atvinnutekjur P90/P10',data:recentYears.map(y=>getP90P10(employDist2554,y)),borderColor:blue,borderWidth:2.5,tension:.3,pointRadius:2},
    ],
  },
  options:{
    responsive:true,maintainAspectRatio:false,
    plugins:{tooltip:{callbacks:{label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y}x`}}},
    scales:{x:{grid:{display:false}},y:{title:{display:true,text:'P90/P10 hlutfall'}}},
  },
});

// ===== CHART 6: Mean vs Median =====
new Chart(document.getElementById('chart-mean-median'),{
  type:'line',
  data:{
    labels:recentYears,
    datasets:[
      {label:'Meðaltal',data:recentYears.map(y=>monthly(totalInc,y)),borderColor:red,borderWidth:2.5,tension:.3,pointRadius:2},
      {label:'Miðgildi',data:recentYears.map(y=>monthly(totalMed,y)),borderColor:blue,borderWidth:2.5,tension:.3,pointRadius:2},
    ],
  },
  options:{
    responsive:true,maintainAspectRatio:false,
    plugins:{tooltip:{callbacks:{label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y} þ.kr./mán.`}}},
    scales:{x:{grid:{display:false}},y:{title:{display:true,text:'þús. kr./mánuði'}}},
  },
});

// ===== CHART 7: Gini =====
const giniYears=GINI.map(r=>Object.keys(r)[0]?r[Object.keys(r)[0]]:null).filter(Boolean);
// Gini data is wide format with year as first column
const giniData=GINI.map(r=>{
  const keys=Object.keys(r);
  return{year:r[keys[0]],gini:parseFloat(r[keys[1]]),giniNoSocial:parseFloat(r[keys[7]])};
}).filter(d=>!isNaN(d.gini));

new Chart(document.getElementById('chart-gini'),{
  type:'line',
  data:{
    labels:giniData.map(d=>d.year),
    datasets:[
      {label:'Gini-stuðull',data:giniData.map(d=>d.gini),borderColor:blue,borderWidth:2.5,tension:.3,pointRadius:3},
      {label:'Gini án félagslegrar aðstoðar',data:giniData.map(d=>d.giniNoSocial),borderColor:red,borderWidth:2,borderDash:[5,3],tension:.3,pointRadius:2},
    ],
  },
  options:{
    responsive:true,maintainAspectRatio:false,
    scales:{x:{grid:{display:false}},y:{title:{display:true,text:'Gini-stuðull'}}},
  },
});

// ===== CHART 8: Gender =====
const genderMean=INCOME_GENDER.filter(r=>r['Tekjur og skattar']?.includes('Heildartekjur')&&r['Eining']?.includes('altal'));
const maleInc=genderMean.find(r=>r['Kyn']?.includes('Karlar'));
const femaleInc=genderMean.find(r=>r['Kyn']?.includes('Konur'));

new Chart(document.getElementById('chart-gender'),{
  type:'line',
  data:{
    labels:recentYears,
    datasets:[
      {label:'Karlar',data:recentYears.map(y=>monthly(maleInc,y)),borderColor:blue,borderWidth:2.5,tension:.3,pointRadius:2},
      {label:'Konur',data:recentYears.map(y=>monthly(femaleInc,y)),borderColor:purple,borderWidth:2.5,tension:.3,pointRadius:2},
    ],
  },
  options:{
    responsive:true,maintainAspectRatio:false,
    plugins:{tooltip:{callbacks:{label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y} þ.kr./mán.`}}},
    scales:{x:{grid:{display:false}},y:{title:{display:true,text:'þús. kr./mánuði'}}},
  },
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()

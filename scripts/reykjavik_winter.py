"""Process Reykjavík environmental operations data for outsourcing proxy analysis."""

import csv
from pathlib import Path


def process_env_ops():
    """Compute wages vs other costs ratio from CKAN environmental ops data."""
    raw = Path("data/raw/reykjavik/umhverfismal_heild.csv")
    output = Path("data/processed/reykjavik_env_ops_ratio.csv")
    output.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    with open(raw, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            # Only "Umhverfismál samtals" in thousands ISK
            if row["Rekstarliðir"] == "Umhverfismál samtals" and row["Eining"] == "Í þús kr.":
                year = int(row["Ár"])
                wages = int(row["Laun og launatengd gjöld"])
                other = int(row["Annar rekstrarkostnaður"])
                total = wages + other
                ratio = other / wages if wages > 0 else 0
                rows.append({
                    "year": year,
                    "wages_thkr": wages,
                    "other_costs_thkr": other,
                    "total_costs_thkr": total,
                    "other_to_wages_ratio": round(ratio, 3),
                })

    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {output}")
    for r in rows:
        bar = "█" * int(r["other_to_wages_ratio"] * 10)
        print(f"  {r['year']}: ratio={r['other_to_wages_ratio']:.2f} {bar}")


if __name__ == "__main__":
    process_env_ops()

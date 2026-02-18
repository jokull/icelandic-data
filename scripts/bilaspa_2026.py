"""
Bílasöluspá 2026 - Forecasting model for Icelandic car market

Based on:
- Current registrations by make and fuel type (Samgöngustofa)
- Policy changes effective Jan 1, 2026
- Trade policy (Iceland-China FTA vs EU tariffs on Chinese EVs)
- Financial health of importers (skatturinn.is annual reports)

Key policy changes 2026:
- EV excise tax: 5% → 0%
- EV subsidy: 900k → 500k ISK
- PHEV excise: 5% → 30% (6x increase!)
- Petrol/diesel excise: 5% → 15% minimum
- New per-km charge: 6.95 ISK/km all vehicles
- Fuel taxes eliminated
"""

import json
from dataclasses import dataclass
from typing import Dict, List
import csv

# === CURRENT MARKET DATA (from Samgöngustofa Power BI, Jan 2026) ===

CURRENT_FLEET = {
    # Fuel type distribution
    "fuel_types": {
        "Bensín": 173_934,
        "Dísel": 151_626,
        "Rafmagn": 39_639,
        "Tengiltvinn": 28_206,
        "Hybrid": 20_916,
        "Annað": 5_177,
    },
    # Top makes by registered vehicles
    "top_makes": {
        "TOYOTA": 52_065,
        "KIA": 21_390,
        "VOLKSWAGEN": 19_683,
        "HYUNDAI": 17_221,
        "FORD": 16_482,
        "NISSAN": 13_944,
        "MERCEDES-BENZ": 12_287,
        "SUZUKI": 11_761,
        "SKODA": 11_488,
        "RENAULT": 9_996,
        "VOLVO": 9_803,
        "TESLA": 9_241,
        "MITSUBISHI": 9_200,
    },
    # Chinese brands
    "chinese_brands": {
        "MG": 1_537,
        "POLESTAR": 1_033,
        "BYD": 853,
        "XPENG": 352,
        "MAXUS": 292,
        "AIWAYS": 126,
    },
}

# 2024 new registrations baseline (estimated from partial data)
NEW_REGISTRATIONS_2024 = {
    "total": 12_500,  # Approximate
    "by_fuel": {
        "Rafmagn": 3_100,  # ~25%
        "Tengiltvinn": 2_500,  # ~20%
        "Dísel": 3_750,  # ~30%
        "Bensín": 2_500,  # ~20%
        "Hybrid": 650,  # ~5%
    },
    "chinese_ev_share": 0.08,  # ~8% of EV market
}

# === POLICY CHANGE IMPACTS ===

@dataclass
class PolicyImpact:
    """Estimated impact of policy changes on segment demand."""
    segment: str
    price_change_pct: float  # Effective price change
    demand_elasticity: float  # Price elasticity of demand

    @property
    def demand_change(self) -> float:
        """Calculate demand change from price change and elasticity."""
        return -self.price_change_pct * self.demand_elasticity

POLICY_IMPACTS = {
    # EVs: -5% excise but -400k subsidy = net effect depends on car price
    # Cheap EV (5M): -250k excise, -400k subsidy = +150k (+3%)
    # Expensive EV (10M): -500k excise, -400k subsidy = -100k (-1%)
    # Average effect: roughly neutral, slight boost to expensive EVs
    "Rafmagn": PolicyImpact("Rafmagn", price_change_pct=-0.02, demand_elasticity=1.2),

    # PHEVs: 5% → 30% excise = massive increase
    # Average PHEV 12M: was 600k tax, now 3.6M = +3M (+25%)
    "Tengiltvinn": PolicyImpact("Tengiltvinn", price_change_pct=0.25, demand_elasticity=1.5),

    # Petrol: 5% → 15% minimum, stricter emissions
    # Average petrol car: +600-800k (+8-10%)
    "Bensín": PolicyImpact("Bensín", price_change_pct=0.09, demand_elasticity=1.3),

    # Diesel: Similar to petrol, higher base prices
    "Dísel": PolicyImpact("Dísel", price_change_pct=0.10, demand_elasticity=1.3),

    # Regular hybrids: Moderate increase
    "Hybrid": PolicyImpact("Hybrid", price_change_pct=0.12, demand_elasticity=1.2),
}

# === CHINESE EV ADVANTAGE ===

# EU tariffs on Chinese EVs (Iceland has 0%)
EU_TARIFFS = {
    "BYD": 0.17 + 0.10,  # 17% countervailing + 10% base = 27%
    "XPENG": 0.207 + 0.10,  # 20.7% + 10% = 30.7%
    "MG": 0.353 + 0.10,  # 35.3% + 10% = 45.3% (SAIC)
    "POLESTAR": 0.207 + 0.10,  # Geely rate
    "MAXUS": 0.353 + 0.10,  # SAIC
    "AIWAYS": 0.207 + 0.10,
}

# This gives Chinese EVs a price advantage in Iceland vs EU
# Assume this drives additional demand growth
CHINA_TARIFF_ADVANTAGE_BOOST = 0.15  # 15% additional demand boost for Chinese EVs


# === FORECASTING MODEL ===

def forecast_2026_sales():
    """
    Forecast 2026 new car registrations by segment and origin.
    """
    results = {
        "baseline_2024": {},
        "forecast_2026": {},
        "change_pct": {},
        "chinese_brands": {},
        "market_share": {},
    }

    total_2024 = NEW_REGISTRATIONS_2024["total"]
    total_2026 = 0

    # Forecast by fuel type
    for fuel, count_2024 in NEW_REGISTRATIONS_2024["by_fuel"].items():
        impact = POLICY_IMPACTS.get(fuel)

        if impact:
            # Apply demand change from policy
            demand_change = impact.demand_change
            count_2026 = count_2024 * (1 + demand_change)
        else:
            count_2026 = count_2024

        # Market adjustment: total market likely contracts slightly due to overall price increases
        market_adjustment = 0.95  # 5% overall market contraction
        count_2026 *= market_adjustment

        results["baseline_2024"][fuel] = int(count_2024)
        results["forecast_2026"][fuel] = int(count_2026)
        results["change_pct"][fuel] = round((count_2026 / count_2024 - 1) * 100, 1)
        total_2026 += count_2026

    results["total_2024"] = total_2024
    results["total_2026"] = int(total_2026)
    results["total_change_pct"] = round((total_2026 / total_2024 - 1) * 100, 1)

    # Chinese EV forecast
    # Current: ~8% of EV market
    # Factors boosting Chinese EVs:
    # 1. No tariffs (vs 27-45% in EU) - price advantage
    # 2. Aggressive expansion (BYD, XPENG ramping up)
    # 3. EVs overall growing

    ev_sales_2026 = results["forecast_2026"]["Rafmagn"]

    chinese_ev_share_2024 = NEW_REGISTRATIONS_2024["chinese_ev_share"]

    # Model Chinese EV share growth
    # Base growth from market momentum
    organic_growth = 1.5  # 50% organic share growth
    # Tariff advantage boost
    tariff_boost = 1 + CHINA_TARIFF_ADVANTAGE_BOOST

    chinese_ev_share_2026 = min(0.30, chinese_ev_share_2024 * organic_growth * tariff_boost)

    chinese_ev_sales_2026 = int(ev_sales_2026 * chinese_ev_share_2026)

    # Allocate among Chinese brands based on current trajectory
    brand_weights = {
        "BYD": 0.35,  # Established, growing
        "MG": 0.30,  # Largest current base
        "XPENG": 0.20,  # New but premium positioning
        "POLESTAR": 0.10,  # Niche premium
        "MAXUS": 0.03,  # Commercial focus
        "AIWAYS": 0.02,  # Small player
    }

    for brand, weight in brand_weights.items():
        sales = int(chinese_ev_sales_2026 * weight)
        eu_tariff = EU_TARIFFS.get(brand, 0.30)
        price_advantage = f"{eu_tariff*100:.0f}% ódýrari en í ESB"

        results["chinese_brands"][brand] = {
            "forecast_2026": sales,
            "eu_tariff": eu_tariff,
            "price_advantage": price_advantage,
        }

    results["chinese_ev_total_2026"] = chinese_ev_sales_2026
    results["chinese_ev_share_2026"] = round(chinese_ev_share_2026 * 100, 1)

    # Market share by fuel type 2026
    for fuel, count in results["forecast_2026"].items():
        results["market_share"][fuel] = round(count / total_2026 * 100, 1)

    return results


def generate_scenario_analysis():
    """
    Generate best/base/worst case scenarios.
    """
    scenarios = {}

    # Base case (from main model)
    base = forecast_2026_sales()
    scenarios["base"] = {
        "name": "Grunnspá",
        "total": base["total_2026"],
        "ev_share": base["market_share"]["Rafmagn"],
        "chinese_ev_share": base["chinese_ev_share_2026"],
        "description": "Miðlungs viðbrögð við stefnubreytingum"
    }

    # Optimistic: EVs grow faster, Chinese brands gain more
    scenarios["optimistic"] = {
        "name": "Bjartsýn",
        "total": int(base["total_2026"] * 1.10),
        "ev_share": base["market_share"]["Rafmagn"] + 5,
        "chinese_ev_share": min(35, base["chinese_ev_share_2026"] + 8),
        "description": "Hröð rafvæðing, kínverskir bílar ná 35% af rafbílamarkaði"
    }

    # Pessimistic: Market contracts more, less EV adoption
    scenarios["pessimistic"] = {
        "name": "Svartsýn",
        "total": int(base["total_2026"] * 0.85),
        "ev_share": base["market_share"]["Rafmagn"] - 3,
        "chinese_ev_share": max(10, base["chinese_ev_share_2026"] - 5),
        "description": "Samdráttur í bílamarkaði, hægari rafvæðing"
    }

    return scenarios


def format_results(results: dict) -> str:
    """Format results for display."""
    lines = []
    lines.append("=" * 60)
    lines.append("BÍLASÖLUSPÁ 2026 - ÍSLAND")
    lines.append("=" * 60)

    lines.append("\n## Heildarmarkaður\n")
    lines.append(f"2024 grunnur: {results['total_2024']:,} nýskráningar")
    lines.append(f"2026 spá:     {results['total_2026']:,} nýskráningar")
    lines.append(f"Breyting:     {results['total_change_pct']:+.1f}%")

    lines.append("\n## Eftir orkugjafa\n")
    lines.append(f"{'Orkugjafi':<15} {'2024':>8} {'2026':>8} {'Breyting':>10} {'Hlutdeild':>10}")
    lines.append("-" * 55)
    for fuel in results["baseline_2024"]:
        b = results["baseline_2024"][fuel]
        f = results["forecast_2026"][fuel]
        c = results["change_pct"][fuel]
        s = results["market_share"][fuel]
        lines.append(f"{fuel:<15} {b:>8,} {f:>8,} {c:>+9.1f}% {s:>9.1f}%")

    lines.append("\n## Kínverskir rafbílar\n")
    lines.append(f"Markaðshlutdeild rafbíla: {results['chinese_ev_share_2026']:.1f}%")
    lines.append(f"Heildarfjöldi:            {results['chinese_ev_total_2026']:,}")
    lines.append("")
    lines.append(f"{'Merki':<12} {'Spá 2026':>10} {'ESB-tollur':>12} {'Forskot Íslands'}")
    lines.append("-" * 55)
    for brand, data in results["chinese_brands"].items():
        lines.append(f"{brand:<12} {data['forecast_2026']:>10,} {data['eu_tariff']*100:>11.0f}% {data['price_advantage']}")

    return "\n".join(lines)


def save_forecast_data(results: dict, scenarios: dict, output_dir: str):
    """Save forecast data to CSV files for Evidence."""
    import os
    os.makedirs(output_dir, exist_ok=True)

    # Fuel type forecast
    with open(f"{output_dir}/forecast_by_fuel.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["fuel_type", "sales_2024", "sales_2026", "change_pct", "market_share_2026"])
        for fuel in results["baseline_2024"]:
            writer.writerow([
                fuel,
                results["baseline_2024"][fuel],
                results["forecast_2026"][fuel],
                results["change_pct"][fuel],
                results["market_share"][fuel],
            ])

    # Chinese brands forecast
    with open(f"{output_dir}/chinese_brands_forecast.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["brand", "forecast_2026", "eu_tariff_pct", "iceland_advantage"])
        for brand, data in results["chinese_brands"].items():
            writer.writerow([
                brand,
                data["forecast_2026"],
                data["eu_tariff"] * 100,
                data["price_advantage"],
            ])

    # Scenarios
    with open(f"{output_dir}/scenarios.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["scenario", "name", "total_sales", "ev_share_pct", "chinese_ev_share_pct", "description"])
        for key, data in scenarios.items():
            writer.writerow([
                key,
                data["name"],
                data["total"],
                data["ev_share"],
                data["chinese_ev_share"],
                data["description"],
            ])

    # Policy impacts summary
    with open(f"{output_dir}/policy_impacts.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["segment", "price_change_pct", "demand_elasticity", "demand_change_pct"])
        for segment, impact in POLICY_IMPACTS.items():
            writer.writerow([
                segment,
                impact.price_change_pct * 100,
                impact.demand_elasticity,
                impact.demand_change * 100,
            ])

    # Summary metrics
    summary = {
        "total_market_2024": results["total_2024"],
        "total_market_2026": results["total_2026"],
        "market_change_pct": results["total_change_pct"],
        "ev_sales_2026": results["forecast_2026"]["Rafmagn"],
        "ev_market_share_2026": results["market_share"]["Rafmagn"],
        "phev_sales_2026": results["forecast_2026"]["Tengiltvinn"],
        "phev_change_pct": results["change_pct"]["Tengiltvinn"],
        "chinese_ev_total_2026": results["chinese_ev_total_2026"],
        "chinese_ev_share_2026": results["chinese_ev_share_2026"],
    }

    with open(f"{output_dir}/summary.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        for k, v in summary.items():
            writer.writerow([k, v])

    print(f"Data saved to {output_dir}/")


if __name__ == "__main__":
    # Run forecast
    results = forecast_2026_sales()
    scenarios = generate_scenario_analysis()

    # Print results
    print(format_results(results))

    print("\n## Sviðsmyndir\n")
    for key, scenario in scenarios.items():
        print(f"{scenario['name']}: {scenario['total']:,} bílar, {scenario['ev_share']:.0f}% rafbílar, {scenario['chinese_ev_share']:.0f}% kínverskir")

    # Save data
    save_forecast_data(results, scenarios, "/Users/jokull/Code/hagstofan/data/processed/bilaspa_2026")

"""
Icelandic take-home salary calculator via payday.is API.

Usage:
    uv run python scripts/laun.py 1000000              # Monthly gross -> take-home
    uv run python scripts/laun.py 1000000 --total-cost  # From employer total cost
    uv run python scripts/laun.py 1000000 --json        # Full JSON breakdown
    uv run python scripts/laun.py 1000000 --union 1.1   # With union fee %
"""

import argparse
import json
import sys

import httpx

API_URL = "https://payday.is/is/ajax/calculator/calculateSalary/"

# 2025 defaults from payday.is
DEFAULTS = {
    "PensionContributionEmployeePercentage": "4.00",
    "PensionContributionEmployerPercentage": "11.50",
    "RehabilitationFundPercentage": "0.10",
    "AdditionalPensionContributionEmployeePercentage": "0",
    "AdditionalPensionContributionEmployerPercentage": "0",
    "IncomeTaxStep1Percentage": "31.49",
    "IncomeTaxStep2Percentage": "37.99",
    "IncomeTaxStep3Percentage": "46.29",
    "InsuranceFeePercentage": "6.35",
    "PersonalTaxAllowancePercentage": "100",
    "SpouseTaxAllowancePercentage": "0",
    "UnionFeePercentage": "0.00",
    "PrivateSectorReliefFundPercentage": "0.00",
    "VacationFundPercentage": "0.00",
    "EducationFundPercentage": "0.00",
}


def calculate(
    salary: int | None = None,
    total_cost: int | None = None,
    *,
    union_fee_pct: float = 0.0,
    personal_allowance_pct: float = 100.0,
    additional_pension_employee_pct: float = 0.0,
    additional_pension_employer_pct: float = 0.0,
) -> dict:
    payload = {
        **DEFAULTS,
        "Salary": str(salary) if salary else None,
        "TotalCost": str(total_cost) if total_cost else None,
        "UnionFeePercentage": f"{union_fee_pct:.2f}",
        "PersonalTaxAllowancePercentage": f"{personal_allowance_pct:.0f}",
        "AdditionalPensionContributionEmployeePercentage": f"{additional_pension_employee_pct:.2f}",
        "AdditionalPensionContributionEmployerPercentage": f"{additional_pension_employer_pct:.2f}",
    }
    resp = httpx.post(
        API_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    resp.raise_for_status()
    result = resp.json()
    if not result.get("success"):
        raise ValueError(f"API error: {result}")
    return result["data"]


def format_krona(amount: int | float) -> str:
    return f"{int(amount):>12,} kr."


def print_summary(data: dict):
    print(f"  Gross salary:       {format_krona(data['salary'])}")
    print(f"  Total employer cost:{format_krona(data['totalCost'])}")
    print()
    print("  Employee deductions:")
    print(f"    Pension (4%):     {format_krona(data['pensionContributionEmployeeTotalAmount'])}")
    if data["additionalPensionContributionEmployeeAmount"]:
        print(f"    Additional pension:{format_krona(data['additionalPensionContributionEmployeeAmount'])}")
    print(f"    Income tax:       {format_krona(data['incomeTaxEmployeeTotalAmount'])}")
    if data["unionFeeAmount"]:
        print(f"    Union fee:        {format_krona(data['unionFeeAmount'])}")
    print(f"    Tax allowance:   -{format_krona(data['personalTaxAllowanceAmount']).strip()}")
    print()
    print(f"  Take-home pay:      {format_krona(data['payoutAmountSalary'])}")
    print()
    print("  Employer costs:")
    print(f"    Pension (11.5%):  {format_krona(data['pensionContributionEmployerTotalAmount'])}")
    print(f"    Insurance (6.35%):{format_krona(data['insuranceFeeAmount'])}")
    pct = data["payoutAmountSalary"] / data["salary"] * 100
    print()
    print(f"  Effective take-home: {pct:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Icelandic salary calculator")
    parser.add_argument("amount", type=int, help="Monthly amount in ISK")
    parser.add_argument("--total-cost", action="store_true", help="Treat amount as employer total cost")
    parser.add_argument("--json", action="store_true", help="Output full JSON")
    parser.add_argument("--union", type=float, default=0.0, help="Union fee percentage (e.g. 1.1)")
    parser.add_argument("--personal-allowance", type=float, default=100.0, help="Personal tax allowance %% (0-200)")
    parser.add_argument("--additional-pension", type=float, default=0.0, help="Additional voluntary pension %% (employee)")
    args = parser.parse_args()

    salary = None if args.total_cost else args.amount
    total_cost = args.amount if args.total_cost else None

    data = calculate(
        salary=salary,
        total_cost=total_cost,
        union_fee_pct=args.union,
        personal_allowance_pct=args.personal_allowance,
        additional_pension_employee_pct=args.additional_pension,
    )

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print_summary(data)


if __name__ == "__main__":
    main()

"""Health probe — payday.is salary calculator.

Contract: `POST /is/ajax/calculator/calculateSalary/` accepts the DEFAULTS
payload from scripts/laun.py and answers `{"success": true, "data": {...}}`.

This upstream is a *calculator*, not a dataset, which makes it unusually
probeable: the response is a pure function of the request, so the probe can
assert arithmetic rather than settle for "some number came back". A round
1,000,000 ISK gross is posted and the derived figures are checked against the
percentages we sent.

The one thing that is genuinely payday's own state — and not ours — is the
personal tax allowance (persónuafsláttur), a constant baked into their server
and revised every January. That is range-checked, never pinned: pinning it would
turn a routine tax-year update into a red probe.

Note the script raises ValueError on `success != true`, so a soft failure here
surfaces as an exception mid-run rather than a bad number.
"""
from __future__ import annotations

import pytest

from scripts.laun import API_URL, DEFAULTS

GROSS = 1_000_000


@pytest.fixture(scope="module")
def data(http):
    """Post exactly what calculate() posts — same payload, same headers."""
    payload = {**DEFAULTS, "Salary": str(GROSS), "TotalCost": None}
    r = http.post(
        API_URL,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    assert r.status_code == 200, f"{r.request.url} -> {r.status_code}: {r.text[:200]}"
    assert r.headers["content-type"].startswith("application/json")

    result = r.json()
    assert result.get("success") is True, (
        f"{r.request.url} -> 200 but success={result.get('success')!r}: {str(result)[:200]}"
    )
    assert "data" in result, f"no 'data' key; got {sorted(result)}"
    return result["data"]


def test_response_carries_the_fields_the_script_prints(data):
    """print_summary() and the skill's documented projection read these keys
    unguarded — a rename is a KeyError, not a degraded number."""
    required = {
        "salary",
        "totalCost",
        "payoutAmountSalary",
        "incomeTaxEmployeeTotalAmount",
        "pensionContributionEmployeeTotalAmount",
        "pensionContributionEmployerTotalAmount",
        "personalTaxAllowanceAmount",
        "insuranceFeeAmount",
        "unionFeeAmount",
        "additionalPensionContributionEmployeeAmount",
    }
    assert required <= set(data), (
        f"response is missing keys {sorted(required - set(data))}; got {sorted(data)}"
    )
    for key in required:
        assert isinstance(data[key], (int, float)), (
            f"{key} is {type(data[key]).__name__}, not numeric: {data[key]!r}"
        )


def test_posted_percentages_are_honoured(data):
    """Guards the failure mode where the API ignores our parameters and answers
    from its own defaults — which would look completely normal in the output.

    Deterministic arithmetic on a round number, so this is exact by
    construction, not a pinned market value.
    """
    assert data["salary"] == GROSS, f"echoed salary {data['salary']} != posted {GROSS}"
    assert data["pensionContributionEmployeeAmount"] == GROSS * 0.04, (
        f"4% employee pension on {GROSS} should be {GROSS * 0.04:.0f}, "
        f"got {data['pensionContributionEmployeeAmount']} — posted rates may be ignored"
    )
    assert data["pensionContributionEmployerAmount"] == GROSS * 0.115, (
        f"11.5% employer pension on {GROSS} should be {GROSS * 0.115:.0f}, "
        f"got {data['pensionContributionEmployerAmount']}"
    )
    # Tryggingagjald is charged on salary *plus employer pension* — not on
    # salary alone, and not including the rehabilitation fund. Derived from the
    # response's own pension figure rather than hardcoded, so this asserts the
    # base is unchanged without restating it.
    fee_base = data["salary"] + data["pensionContributionEmployerAmount"]
    assert data["insuranceFeeAmount"] == pytest.approx(fee_base * 0.0635, abs=1), (
        f"6.35% tryggingagjald on a base of {fee_base:.0f} (salary + employer "
        f"pension) should be ~{fee_base * 0.0635:.0f}, got {data['insuranceFeeAmount']} — "
        f"the assessment base may have changed"
    )


def test_the_take_home_identity_holds(data):
    """gross - employee deductions = payout, and gross + employer costs =
    total cost. If either identity breaks the calculator has changed shape and
    every derived number in the repo is suspect."""
    assert data["payoutAmountSalary"] == data["salary"] - data["employeeContributionAmount"], (
        f"{data['salary']} - {data['employeeContributionAmount']} != "
        f"{data['payoutAmountSalary']}"
    )
    assert data["totalCost"] == data["salary"] + data["employerContributionAmount"], (
        f"{data['salary']} + {data['employerContributionAmount']} != {data['totalCost']}"
    )
    assert 0 < data["payoutAmountSalary"] < data["salary"], (
        f"implausible take-home {data['payoutAmountSalary']} on {data['salary']} gross"
    )


def test_personal_tax_allowance_is_plausible(data):
    """Payday's own constant, revised each January — range-checked, not pinned.

    The band is wide enough to absorb years of indexation and tight enough to
    catch the allowance being dropped (0) or the field changing units.
    """
    allowance = data["personalTaxAllowanceAmount"]
    assert 50_000 < allowance < 150_000, (
        f"persónuafsláttur of {allowance} ISK/mo is outside the plausible band — "
        f"either the field changed units or the allowance was restructured"
    )

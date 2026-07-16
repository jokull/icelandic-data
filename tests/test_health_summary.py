"""Tests for scripts/health_summary.py.

Fast and offline — these exercise the reporting layer against synthetic JUnit
XML, never the network. The probes themselves live in tests/health/ and are
marked `health` + `slow`, so PR CI runs these and not those.
"""
from __future__ import annotations

import json

import pytest

from scripts import health_summary as hs

# --------------------------------------------------------------------------
# Fixtures — synthetic JUnit XML mirroring what pytest emits
# --------------------------------------------------------------------------

_PASS = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="2">
  <testcase classname="tests.health.test_hagstofan" name="test_catalog" time="0.84"/>
  <testcase classname="tests.health.test_hagstofan" name="test_query" time="0.30"/>
</testsuite></testsuites>
"""

_FAIL = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="1">
  <testcase classname="tests.health.test_landlaeknir" name="test_report" time="14.22">
    <failure message="AssertionError: expected Power BI report page not found">long traceback</failure>
  </testcase>
</testsuite></testsuites>
"""

_SKIP = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="1">
  <testcase classname="tests.health.test_skatturinn" name="test_login" time="0">
    <skipped message="Requires credentials">skipped</skipped>
  </testcase>
</testsuite></testsuites>
"""

_ERROR = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="1">
  <testcase classname="tests.health.test_sedlabanki" name="test_sdmx" time="30.65">
    <error message="Failed: SDMX host unreachable: ConnectTimeout: timed out">tb</error>
  </testcase>
</testsuite></testsuites>
"""


def _xml(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


# --------------------------------------------------------------------------
# Parsing + classification
# --------------------------------------------------------------------------


def test_healthy_responses_pass(tmp_path):
    results = hs.aggregate(hs.parse(_xml(tmp_path, "r.xml", _PASS), "required"))
    assert [r.source for r in results] == ["hagstofan"]
    assert results[0].status == "healthy"
    # Durations sum across a source's probes.
    assert results[0].duration_seconds == pytest.approx(1.14)


def test_required_failure_is_failed_and_keeps_the_assertion(tmp_path):
    results = hs.aggregate(hs.parse(_xml(tmp_path, "r.xml", _FAIL), "required"))
    assert results[0].status == "failed"
    # The failed invariant must survive into the report, or it isn't actionable.
    assert "Power BI report page not found" in results[0].message


def test_same_failure_in_degraded_lane_is_only_degraded(tmp_path):
    """Lane, not outcome, is what separates degraded from failed."""
    results = hs.aggregate(hs.parse(_xml(tmp_path, "d.xml", _FAIL), "degraded"))
    assert results[0].status == "degraded"


def test_transient_connect_error_is_classified_and_reported(tmp_path):
    results = hs.aggregate(hs.parse(_xml(tmp_path, "d.xml", _ERROR), "degraded"))
    assert results[0].status == "degraded"
    assert "ConnectTimeout" in results[0].message


def test_skipped_source_is_reported_not_failed(tmp_path):
    results = hs.aggregate(hs.parse(_xml(tmp_path, "r.xml", _SKIP), "required"))
    assert results[0].status == "skipped"
    assert "credentials" in results[0].message


def test_missing_file_yields_no_cases(tmp_path):
    assert hs.parse(tmp_path / "absent.xml", "required") == []


def test_worst_status_wins_across_a_sources_probes(tmp_path):
    cases = hs.parse(_xml(tmp_path, "r.xml", _PASS), "required")
    cases += [("hagstofan", "failed", "boom", 1.0)]
    results = hs.aggregate(cases)
    assert len(results) == 1
    assert results[0].status == "failed"
    assert results[0].message == "boom"


def test_failed_sources_sort_first(tmp_path):
    cases = hs.parse(_xml(tmp_path, "r.xml", _PASS), "required")
    cases += hs.parse(_xml(tmp_path, "f.xml", _FAIL), "required")
    results = hs.aggregate(cases)
    assert [r.status for r in results] == ["failed", "healthy"]


# --------------------------------------------------------------------------
# Output + exit codes
# --------------------------------------------------------------------------


def test_json_output_is_valid_and_shaped(tmp_path, capsys):
    out = tmp_path / "health.json"
    code = hs.main(["--required", str(_xml(tmp_path, "r.xml", _PASS)), "--json", str(out)])
    assert code == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"] == {"healthy": 1, "degraded": 0, "failed": 0, "skipped": 0}
    assert payload["results"][0]["source"] == "hagstofan"
    assert set(payload["results"][0]) == {
        "source", "status", "message", "duration_seconds", "details",
    }


def test_exit_code_is_nonzero_only_when_a_required_source_fails(tmp_path):
    req = _xml(tmp_path, "r.xml", _PASS)
    fail = _xml(tmp_path, "f.xml", _FAIL)

    assert hs.main(["--required", str(req)]) == 0
    assert hs.main(["--required", str(fail)]) == 1
    # A degraded source alone must not wake anyone.
    assert hs.main(["--required", str(req), "--degraded", str(fail)]) == 0


def test_no_results_is_an_error_not_a_pass(tmp_path):
    """An empty run means pytest never ran — that must not look healthy."""
    assert hs.main(["--required", str(tmp_path / "absent.xml")]) == 2


def test_markdown_summary_is_appended(tmp_path):
    md = tmp_path / "summary.md"
    md.write_text("existing\n", encoding="utf-8")
    hs.main([
        "--required", str(_xml(tmp_path, "r.xml", _PASS)),
        "--degraded", str(_xml(tmp_path, "d.xml", _FAIL)),
        "--markdown", str(md),
    ])
    body = md.read_text(encoding="utf-8")
    assert body.startswith("existing\n")          # appended, not clobbered
    assert "1 healthy, 1 degraded, 0 failed" in body
    assert "`landlaeknir`" in body


def test_headline_counts(tmp_path):
    cases = hs.parse(_xml(tmp_path, "r.xml", _PASS), "required")
    cases += hs.parse(_xml(tmp_path, "f.xml", _FAIL), "required")
    cases += hs.parse(_xml(tmp_path, "s.xml", _SKIP), "required")
    assert hs.headline(hs.aggregate(cases)) == (
        "Data-source health: 1 healthy, 0 degraded, 1 failed, 1 skipped"
    )

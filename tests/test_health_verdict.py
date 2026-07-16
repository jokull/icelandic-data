"""Tests for scripts/health_verdict.py — the flake-vs-dead call.

Fast and offline. This is the logic that decides whether a red wakes someone,
so the boundaries (2 vs 3 in a row, infra vs structural, gap vs downtime) are
pinned down explicitly rather than left to drift.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scripts import health_verdict as hv

NOW = datetime(2026, 7, 16, 6, 17, tzinfo=timezone.utc)


def _row(source="hagstofan", status="healthy", days_ago=0, kind="", error_class="", message=""):
    return {
        "ts": (NOW - timedelta(days=days_ago)).isoformat(),
        "source": source,
        "status": status,
        "error_class": error_class,
        "kind": kind,
        "duration_s": 0.5,
        "message": message,
        "run_url": "",
    }


def _infra(days_ago):
    return _row(
        status="degraded", days_ago=days_ago, kind="infra",
        error_class="ConnectTimeout", message="ConnectTimeout: timed out",
    )


def _structural(days_ago):
    return _row(
        status="failed", days_ago=days_ago, kind="structural",
        error_class="AssertionError", message="AssertionError: expected 'Ár' dimension",
    )


def _history(tmp_path, rows):
    p = tmp_path / "history.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


# --------------------------------------------------------------------------
# The core discrimination
# --------------------------------------------------------------------------


def test_single_failure_between_passes_is_flaky_not_dead():
    """The whole point: one red is a flake until proven otherwise."""
    rows = [_row(days_ago=3), _infra(2), _row(days_ago=1), _row(days_ago=0)]
    v = hv.judge("hagstofan", rows)
    assert v.verdict == "flaky"
    assert not v.gating
    assert v.uptime == 0.75


def test_three_consecutive_infra_failures_is_dead():
    rows = [_row(days_ago=5), _row(days_ago=4), _infra(2), _infra(1), _infra(0)]
    v = hv.judge("sedlabanki", rows)
    assert v.verdict == "dead"
    assert v.streak == 3
    assert v.gating


def test_two_consecutive_infra_failures_is_not_yet_dead():
    """DEAD_AFTER is 3 — two in a row still gets the benefit of the doubt."""
    rows = [_row(days_ago=5), _row(days_ago=4), _infra(1), _infra(0)]
    v = hv.judge("sedlabanki", rows)
    assert v.verdict == "flaky"
    assert not v.gating


def test_two_consecutive_structural_failures_is_broken():
    """Structural convicts faster: a service that answers wrong has changed."""
    rows = [_row(days_ago=5), _row(days_ago=4), _structural(1), _structural(0)]
    v = hv.judge("hagstofan", rows)
    assert v.verdict == "broken"
    assert v.gating
    assert v.kind == "structural"
    assert "Ár" in v.last_error


def test_single_structural_failure_is_not_yet_broken():
    rows = [_row(days_ago=3), _row(days_ago=2), _row(days_ago=1), _structural(0)]
    assert hv.judge("hagstofan", rows).verdict == "flaky"


def test_recovery_resets_the_streak():
    rows = [_infra(4), _infra(3), _row(days_ago=2), _infra(1), _row(days_ago=0)]
    v = hv.judge("umferd", rows)
    assert v.streak == 0
    assert v.verdict == "flaky"
    assert not v.gating


def test_structural_streak_resets_on_an_infra_failure():
    """A structural run then an infra run is not 2 consecutive structurals."""
    rows = [_row(days_ago=4), _structural(2), _infra(1), _structural(0)]
    v = hv.judge("hagstofan", rows)
    assert v.verdict != "broken"
    assert v.streak == 3  # non-healthy streak, but not a structural one


def test_all_healthy_is_healthy():
    rows = [_row(days_ago=i) for i in range(5)]
    v = hv.judge("vedur", rows)
    assert v.verdict == "healthy"
    assert v.uptime == 1.0
    assert not v.gating


# --------------------------------------------------------------------------
# Missing != down
# --------------------------------------------------------------------------


def test_a_gap_in_observations_is_not_downtime():
    """GitHub can drop scheduled runs. Absent rows must not read as failures."""
    rows = [_row(days_ago=20), _row(days_ago=1), _row(days_ago=0)]
    v = hv.judge("vedur", rows)
    assert v.verdict == "healthy"
    assert v.uptime == 1.0
    assert v.observations == 3  # observed, not elapsed days


def test_uptime_is_over_observations_not_calendar():
    rows = [_row(days_ago=10), _infra(9)]
    v = hv.judge("co2", rows)
    assert v.observations == 2
    assert v.uptime == 0.5


def test_skipped_is_not_an_observation():
    rows = [_row(days_ago=2), _row(source="skatturinn", status="skipped", days_ago=1)]
    v = hv.judge("x", rows)
    assert v.observations == 1
    assert v.uptime == 1.0


def test_only_skipped_is_unknown():
    rows = [_row(status="skipped", days_ago=i) for i in range(3)]
    v = hv.judge("skatturinn", rows)
    assert v.verdict == "unknown"
    assert v.uptime is None
    assert not v.gating


def test_one_observation_is_not_enough_to_judge():
    assert hv.judge("new-source", [_row(days_ago=0)]).verdict == "unknown"


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def test_window_excludes_old_rows(tmp_path, monkeypatch):
    p = _history(tmp_path, [_row(days_ago=400), _row(days_ago=0)])
    # judge relative to NOW rather than wall clock
    monkeypatch.setattr(hv, "datetime", _FrozenDatetime)
    by_source = hv.load(p, window_days=30)
    assert len(by_source["hagstofan"]) == 1


def test_corrupt_line_does_not_sink_the_report(tmp_path, monkeypatch):
    p = tmp_path / "history.jsonl"
    p.write_text(
        json.dumps(_row(days_ago=0)) + "\n"
        + "{ this is not json\n"
        + "\n"
        + json.dumps(_row(source="vedur", days_ago=0)) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(hv, "datetime", _FrozenDatetime)
    by_source = hv.load(p, window_days=30)
    assert set(by_source) == {"hagstofan", "vedur"}


def test_missing_history_file_is_empty_not_an_error(tmp_path):
    assert hv.load(tmp_path / "absent.jsonl", 30) == {}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


def test_exit_code_gates_on_dead_and_broken_only(tmp_path, monkeypatch):
    monkeypatch.setattr(hv, "datetime", _FrozenDatetime)

    flaky = _history(tmp_path, [_row(days_ago=2), _infra(1), _row(days_ago=0)])
    assert hv.main(["--history", str(flaky)]) == 0

    dead = _history(tmp_path, [_row(days_ago=5), _infra(2), _infra(1), _infra(0)])
    assert hv.main(["--history", str(dead)]) == 1

    broken = _history(tmp_path, [_row(days_ago=5), _structural(1), _structural(0)])
    assert hv.main(["--history", str(broken)]) == 1


def test_no_history_is_not_a_failure(tmp_path):
    """First run, or a fresh window — nothing to judge is not a red."""
    assert hv.main(["--history", str(tmp_path / "absent.jsonl")]) == 0


def test_json_output_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(hv, "datetime", _FrozenDatetime)
    p = _history(tmp_path, [_row(days_ago=5), _infra(2), _infra(1), _infra(0)])
    out = tmp_path / "verdicts.json"
    hv.main(["--history", str(p), "--json", str(out)])

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["window_days"] == 30
    v = payload["verdicts"][0]
    assert v["source"] == "hagstofan"
    assert v["verdict"] == "dead"
    assert v["streak"] == 3
    assert set(v) == {
        "source", "verdict", "streak", "observations", "uptime",
        "last_ok", "last_error", "error_class", "kind",
    }


def test_markdown_is_appended_with_gating_sources_first(tmp_path, monkeypatch):
    monkeypatch.setattr(hv, "datetime", _FrozenDatetime)
    rows = [_row(source="vedur", days_ago=i) for i in range(4)]
    rows += [_structural(1), _structural(0)]
    p = _history(tmp_path, rows)
    md = tmp_path / "summary.md"
    md.write_text("existing\n", encoding="utf-8")

    hv.main(["--history", str(p), "--markdown", str(md)])
    body = md.read_text(encoding="utf-8")
    assert body.startswith("existing\n")
    # broken sorts above healthy
    assert body.index("`hagstofan`") < body.index("`vedur`")

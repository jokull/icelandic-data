"""Decide, from health history, which sources are actually broken.

A single red tells you almost nothing. Icelandic public APIs blink; a probe that
fails at 06:17 and passes at 06:17 tomorrow was a flake, and paging on it is how
a monitor teaches you to ignore it. So the gate is a *verdict over history*, not
over today:

    dead    — 3+ consecutive non-healthy observations (infra: unreachable/sick)
    broken  — 2+ consecutive *structural* failures: the service answered and
              answered wrong. Schema drift, expired dashboard id, revoked key.
              The skill is now lying about the source, and needs updating.
    flaky   — failed within the window but recovered; recorded, not actionable
    healthy — clean across the window
    unknown — too few observations to judge yet

Structural failures convict faster than infra ones because they essentially
never self-heal: a service healthy enough to fail your assertion is a service
that is up and has changed.

Streaks count *consecutive observations*, never calendar days. GitHub documents
that scheduled runs can be dropped entirely, so a gap means "not observed", not
"down" — and uptime is healthy/observed, never healthy/elapsed.

Usage:
    uv run python scripts/health_verdict.py --history health/history.jsonl
    uv run python scripts/health_verdict.py --history h.jsonl --markdown "$GITHUB_STEP_SUMMARY"

Exits non-zero when any source is dead or broken.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

Verdict = Literal["dead", "broken", "flaky", "healthy", "unknown"]

# Consecutive non-healthy observations before we call a source dead.
DEAD_AFTER = 3
# Consecutive structural failures before we call the skill broken. Lower,
# because structural failures do not recover on their own.
BROKEN_AFTER = 2
# Below this many observations we decline to judge rather than guess.
MIN_OBSERVATIONS = 2

# The README badge deliberately has a much higher bar than the pager. It is
# read by strangers deciding whether to trust this repo, so it should report
# settled facts, not weather. A source must be down this long before it turns
# the badge red — a badge that flaps is worse than no badge.
BADGE_DOWN_DAYS = 7

_RANK: dict[Verdict, int] = {"broken": 0, "dead": 1, "flaky": 2, "unknown": 3, "healthy": 4}
_LABEL: dict[Verdict, str] = {
    "dead": "DEAD",
    "broken": "BROKEN",
    "flaky": "FLAKY",
    "healthy": "HEALTHY",
    "unknown": "UNKNOWN",
}
_GATING: set[Verdict] = {"dead", "broken"}


@dataclass
class SourceVerdict:
    source: str
    verdict: Verdict
    streak: int
    observations: int
    uptime: float | None
    last_ok: str | None
    last_error: str
    error_class: str
    kind: str
    down_days: float | None = None

    @property
    def gating(self) -> bool:
        return self.verdict in _GATING


def down_for_days(v: SourceVerdict, threshold: float = BADGE_DOWN_DAYS) -> bool:
    """Has this source been failing continuously for `threshold` days?

    Measured as wall-clock since the last success, NOT as a count of failed
    observations. A run that never happened is not evidence of a source being
    down, so counting observations would let a week of dropped CI runs
    masquerade as a week of outage. Time since last_ok cannot be faked that way.

    A source that has never once succeeded has no last_ok; it is excluded rather
    than treated as infinitely down, because that is far more likely to be a
    broken probe than a source that never existed.
    """
    return bool(v.gating and v.down_days is not None and v.down_days >= threshold)


def load(path: pathlib.Path, window_days: int) -> dict[str, list[dict]]:
    """Read JSONL history, newest-last, filtered to the window."""
    if not path.exists():
        return {}
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    by_source: dict[str, list[dict]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            ts = datetime.fromisoformat(row["ts"])
        except (json.JSONDecodeError, KeyError, ValueError):
            # A corrupt line must not take the whole report down.
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if ts < cutoff:
            continue
        by_source.setdefault(row["source"], []).append(row)
    for rows in by_source.values():
        rows.sort(key=lambda r: r["ts"])
    return by_source


def judge(source: str, rows: list[dict]) -> SourceVerdict:
    # "skipped" is an absence of observation (credentials missing, probe not
    # run) — it neither breaks a streak nor counts against uptime.
    observed = [r for r in rows if r["status"] != "skipped"]
    if not observed:
        return SourceVerdict(source, "unknown", 0, 0, None, None, "", "", "")

    healthy = [r for r in observed if r["status"] == "healthy"]
    uptime = len(healthy) / len(observed)
    last_ok = healthy[-1]["ts"] if healthy else None

    # Walk backwards from the newest observation.
    streak = 0
    structural_streak = 0
    for row in reversed(observed):
        if row["status"] == "healthy":
            break
        streak += 1
        if row.get("kind") == "structural":
            structural_streak += 1
        else:
            structural_streak = 0

    newest = observed[-1]
    last_error = newest.get("message", "") if newest["status"] != "healthy" else ""
    error_class = newest.get("error_class", "") if newest["status"] != "healthy" else ""
    kind = newest.get("kind", "") if newest["status"] != "healthy" else ""

    down_days = None
    if last_ok and newest["status"] != "healthy":
        then = datetime.fromisoformat(last_ok)
        if then.tzinfo is None:
            then = then.replace(tzinfo=UTC)
        down_days = round((datetime.now(UTC) - then).total_seconds() / 86400, 2)

    if structural_streak >= BROKEN_AFTER:
        verdict: Verdict = "broken"
    elif streak >= DEAD_AFTER:
        verdict = "dead"
    elif len(observed) < MIN_OBSERVATIONS:
        # One observation is not evidence either way — not even of health.
        verdict = "unknown" if streak else "unknown"
    elif streak or uptime < 1.0:
        verdict = "flaky"
    else:
        verdict = "healthy"

    return SourceVerdict(
        source=source,
        verdict=verdict,
        streak=streak,
        observations=len(observed),
        uptime=round(uptime, 4),
        last_ok=last_ok,
        last_error=last_error[:200],
        error_class=error_class,
        kind=kind,
        down_days=down_days,
    )


def badge(verdicts: list[SourceVerdict], threshold: float = BADGE_DOWN_DAYS) -> dict:
    """shields.io endpoint payload — https://shields.io/badges/endpoint-badge

    Rendered in the README via:
        img.shields.io/endpoint?url=<raw url of this file on health-history>

    No hosting, no service: shields fetches the JSON we already commit.
    """
    judged = [v for v in verdicts if v.verdict != "unknown"]
    down = [v for v in judged if down_for_days(v, threshold)]

    if not judged:
        message, color = "no data", "lightgrey"
    elif down:
        worst = max(down, key=lambda v: v.down_days or 0)
        if len(down) == 1:
            message = f"{worst.source} down {worst.down_days:.0f}d"
        else:
            message = f"{len(down)} sources down"
        color = "red"
    else:
        message, color = f"{len(judged)}/{len(judged)} healthy", "brightgreen"

    return {
        "schemaVersion": 1,
        "label": "data sources",
        "message": message,
        "color": color,
    }


def judge_all(by_source: dict[str, list[dict]]) -> list[SourceVerdict]:
    verdicts = [judge(source, rows) for source, rows in by_source.items()]
    return sorted(verdicts, key=lambda v: (_RANK[v.verdict], v.source))


def headline(verdicts: list[SourceVerdict]) -> str:
    c: dict[str, int] = {}
    for v in verdicts:
        c[v.verdict] = c.get(v.verdict, 0) + 1
    parts = [f"{c[k]} {k}" for k in ("dead", "broken", "flaky", "unknown", "healthy") if c.get(k)]
    return "Source verdicts: " + (", ".join(parts) if parts else "no history yet")


def render_text(verdicts: list[SourceVerdict]) -> str:
    lines = [headline(verdicts)]
    for v in verdicts:
        up = "  —  " if v.uptime is None else f"{v.uptime:5.0%}"
        note = v.last_error or (f"streak {v.streak}" if v.streak else "")
        lines.append(
            f"{_LABEL[v.verdict]:<8} {v.source:<24} up={up} n={v.observations:<4} {note}"[:200]
        )
    return "\n".join(lines)


def render_markdown(verdicts: list[SourceVerdict], window_days: int) -> str:
    icon = {"dead": "💀", "broken": "🔧", "flaky": "🌊", "healthy": "✅", "unknown": "❔"}
    lines = [
        f"## {headline(verdicts)}",
        "",
        f"_Verdicts over the last {window_days} days of observations. "
        f"dead = {DEAD_AFTER}+ consecutive failures; broken = {BROKEN_AFTER}+ consecutive "
        f"structural failures (the skill needs updating); flaky = recovered on its own._",
        "",
        "| | Source | Uptime | Obs | Streak | Detail |",
        "|---|---|---|---|---|---|",
    ]
    for v in verdicts:
        up = "—" if v.uptime is None else f"{v.uptime:.0%}"
        detail = (v.last_error or "").replace("|", "\\|")[:120] or "—"
        lines.append(
            f"| {icon[v.verdict]} | `{v.source}` | {up} | {v.observations} | "
            f"{v.streak or '—'} | {detail} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history", type=pathlib.Path, required=True, help="JSONL history file")
    ap.add_argument("--window-days", type=int, default=30, help="lookback window (default 30)")
    ap.add_argument("--json", type=pathlib.Path, help="write verdicts here")
    ap.add_argument("--markdown", type=pathlib.Path, help="append a markdown summary here")
    ap.add_argument(
        "--badge",
        type=pathlib.Path,
        help="write a shields.io endpoint JSON here (README badge)",
    )
    ap.add_argument(
        "--badge-down-days",
        type=float,
        default=BADGE_DOWN_DAYS,
        help=f"days a source must be down before the badge goes red (default {BADGE_DOWN_DAYS})",
    )
    args = ap.parse_args(argv)

    by_source = load(args.history, args.window_days)
    if not by_source:
        # No history is not a failure — it is the first run, or a fresh window.
        print(f"no observations in {args.history} within {args.window_days}d", file=sys.stderr)
        if args.badge:
            # Still write the badge, or a stale one lingers in the README
            # claiming health we can no longer vouch for.
            args.badge.write_text(json.dumps(badge([]), indent=2) + "\n", encoding="utf-8")
        return 0

    verdicts = judge_all(by_source)
    print(render_text(verdicts))

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "window_days": args.window_days,
                    "generated": datetime.now(UTC).isoformat(timespec="seconds"),
                    "verdicts": [asdict(v) for v in verdicts],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    if args.markdown:
        with args.markdown.open("a", encoding="utf-8") as fh:
            fh.write(render_markdown(verdicts, args.window_days))
    if args.badge:
        payload = badge(verdicts, args.badge_down_days)
        args.badge.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"badge: {payload['message']} ({payload['color']})", file=sys.stderr)

    gating = [v for v in verdicts if v.gating]
    if gating:
        print(
            "\ngating: " + ", ".join(f"{v.source} ({v.verdict})" for v in gating),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

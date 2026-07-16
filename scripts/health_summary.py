"""Render data-source health results from pytest JUnit XML.

Aggregates per-source status from one or more JUnit files, each tagged with the
lane it came from:

    uv run python scripts/health_summary.py \
        --required health-required.xml \
        --degraded health-degraded.xml \
        --json health-results.json \
        --markdown "$GITHUB_STEP_SUMMARY"

Lanes, and why there are two: pytest models pass/fail, not healthy/degraded/failed.
Rather than build a parallel health framework to express that one distinction, the
scheduled run invokes pytest twice — once for hard invariants (gates the job) and
once for staleness / known-soft probes (reports only) — and this script merges them.

Exit code is non-zero only when a *required* probe failed.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import asdict, dataclass, field
from typing import Literal
from xml.etree import ElementTree

Status = Literal["healthy", "degraded", "failed", "skipped"]

_RANK: dict[Status, int] = {"failed": 0, "degraded": 1, "skipped": 2, "healthy": 3}
_LABEL: dict[Status, str] = {
    "healthy": "HEALTHY",
    "degraded": "DEGRADED",
    "failed": "FAILED",
    "skipped": "SKIPPED",
}


@dataclass
class HealthResult:
    source: str
    status: Status
    message: str
    duration_seconds: float
    details: dict[str, object] = field(default_factory=dict)


def _source_of(classname: str, name: str) -> str:
    """tests.health.test_hagstofan -> hagstofan"""
    for part in classname.split("."):
        if part.startswith("test_"):
            return part[len("test_") :]
    return name


def _first_line(text: str | None) -> str:
    if not text:
        return ""
    for line in text.strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def parse(path: pathlib.Path, lane: str) -> list[tuple[str, Status, str, float]]:
    """Return (source, status, message, duration) per testcase."""
    if not path.exists():
        return []
    out = []
    for case in ElementTree.parse(path).getroot().iter("testcase"):
        source = _source_of(case.get("classname", ""), case.get("name", ""))
        duration = float(case.get("time") or 0.0)

        failure = case.find("failure") if case.find("failure") is not None else case.find("error")
        skipped = case.find("skipped")

        if failure is not None:
            # A failure in the degraded lane means "up but not right", not "down".
            status: Status = "failed" if lane == "required" else "degraded"
            message = _first_line(failure.get("message") or failure.text)
        elif skipped is not None:
            status = "skipped"
            message = _first_line(skipped.get("message")) or "skipped"
        else:
            status = "healthy"
            message = ""
        out.append((source, status, message, duration))
    return out


def aggregate(cases: list[tuple[str, Status, str, float]]) -> list[HealthResult]:
    by_source: dict[str, list[tuple[Status, str, float]]] = {}
    for source, status, message, duration in cases:
        by_source.setdefault(source, []).append((status, message, duration))

    results = []
    for source, entries in sorted(by_source.items()):
        worst = min((s for s, _, _ in entries), key=lambda s: _RANK[s])
        total = sum(d for _, _, d in entries)
        # Surface the message from the worst probe — that is the actionable one.
        message = next(
            (m for s, m, _ in entries if s == worst and m),
            f"{len(entries)} probe(s) passed",
        )
        results.append(
            HealthResult(
                source=source,
                status=worst,
                message=message,
                duration_seconds=round(total, 2),
                details={
                    "probes": len(entries),
                    "failed": sum(1 for s, _, _ in entries if s in ("failed", "degraded")),
                },
            )
        )
    return sorted(results, key=lambda r: (_RANK[r.status], r.source))


def counts(results: list[HealthResult]) -> dict[str, int]:
    out = {"healthy": 0, "degraded": 0, "failed": 0, "skipped": 0}
    for r in results:
        out[r.status] += 1
    return out


def headline(results: list[HealthResult]) -> str:
    c = counts(results)
    return (
        f"Data-source health: {c['healthy']} healthy, {c['degraded']} degraded, "
        f"{c['failed']} failed"
        + (f", {c['skipped']} skipped" if c["skipped"] else "")
    )


def render_text(results: list[HealthResult]) -> str:
    lines = [headline(results)]
    for r in results:
        dur = "    -  " if r.status == "skipped" else f"{r.duration_seconds:6.2f}s"
        lines.append(f"{_LABEL[r.status]:<9} {r.source:<26} {dur}  {r.message}"[:200])
    return "\n".join(lines)


def render_markdown(results: list[HealthResult]) -> str:
    icon = {"healthy": "✅", "degraded": "⚠️", "failed": "❌", "skipped": "⏭️"}
    lines = [f"## {headline(results)}", "", "| | Source | Time | Detail |", "|---|---|---|---|"]
    for r in results:
        dur = "—" if r.status == "skipped" else f"{r.duration_seconds:.2f}s"
        detail = r.message.replace("|", "\\|")[:160] or "—"
        lines.append(f"| {icon[r.status]} | `{r.source}` | {dur} | {detail} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--required", type=pathlib.Path, help="JUnit XML from the required lane")
    ap.add_argument("--degraded", type=pathlib.Path, help="JUnit XML from the degraded lane")
    ap.add_argument("--json", type=pathlib.Path, help="write JSON results here")
    ap.add_argument("--markdown", type=pathlib.Path, help="append a markdown summary here")
    args = ap.parse_args(argv)

    cases = []
    if args.required:
        cases += parse(args.required, "required")
    if args.degraded:
        cases += parse(args.degraded, "degraded")

    if not cases:
        print("no health results found — did pytest run?", file=sys.stderr)
        return 2

    results = aggregate(cases)
    print(render_text(results))

    if args.json:
        args.json.write_text(
            json.dumps(
                {"summary": counts(results), "results": [asdict(r) for r in results]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    if args.markdown:
        with args.markdown.open("a", encoding="utf-8") as fh:
            fh.write(render_markdown(results))

    # Only a required failure is worth waking someone for.
    return 1 if counts(results)["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

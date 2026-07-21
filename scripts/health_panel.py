"""Render one status light per source, as a tiny standalone SVG dot.

The lights live in the README's own source tables — a coloured dot in the first
column of the row that already describes the source, so you read "what is this"
and "is it up" in one glance instead of cross-referencing a separate panel
against a table.

The obvious way to do that is to write emoji into the markdown and re-commit the
README nightly. That is rejected on purpose: it would put a daily bot commit on
main forever, and main's history should be about the project, not about lights.

So each dot is an <img> instead. The pixels live on the `health-history` branch
next to history.jsonl and badge.json; the README holds nothing but static URLs
pointing at them. The lights change daily, the README never does — the artifact
is deanchored from the codebase. Same trick as the shields badge.

    uv run python scripts/health_panel.py --history health/history.jsonl -o dots/

One consequence, accepted: an <img> is opaque, so the SVG's <title> never
surfaces as a tooltip and a dot cannot carry its own uptime/error detail. The
badge is the headline and the workflow summary is the detail view; these are
just the lights. Keeping the README static is worth more than a hover.

A dot is emitted for every known probe, not just those with history — a source
that has never reported still needs a file at its URL, or the README renders a
broken-image icon, which reads as "this repo is unmaintained" rather than "this
source has no observations yet".
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from scripts.health_verdict import judge_all, load  # noqa: E402

# Mid-tone fills, legible against both the light and dark GitHub themes. An
# <img> cannot see the viewer's theme, so the colour has to work in both — no
# prefers-color-scheme escape hatch here.
COLOR = {
    "healthy": "#2da44e",
    "flaky": "#d29922",
    "dead": "#cf222e",
    "broken": "#cf222e",
    "unknown": "#8b949e",
}

# Every probe in tests/health/, so a source with no history still resolves to a
# grey dot rather than a 404. Kept as data rather than globbed from the test
# directory: this script also runs against a history file alone.
PROBES = [
    "byggdastofnun", "car", "co2", "domstolar", "eea_sdi", "farsaeld_barna",
    "energy", "ferdamalastofa", "fiskistofa", "fjarlog", "fuel", "gengi", "hafogvatn", "hagstofan", "heimsmarkmid",
    "hms", "landlaeknir", "laun", "lmi", "lmi_hrl", "loftgaedi",
    "maelabord_landbunadarins", "maskina", "nasdaq", "natt", "opnirreikningar",
    "reykjavik", "rikisreikningur", "samgongustofa", "sedlabanki", "skatturinn",
    "skipulagsmal", "skodanakannanir", "tekjusagan", "tenders", "umferd", "vedur",
    "ust_gis", "velsaeldarvisar", "vernd", "vinnumalastofnun",
]

SIZE = 12


def dot(color: str, label: str) -> str:
    """One 12px light. Plain shapes only — GitHub sanitises SVG and camo-proxies it."""
    r = SIZE / 2 - 1
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
        f'viewBox="0 0 {SIZE} {SIZE}" role="img" aria-label="{label}">'
        f'<circle cx="{SIZE / 2}" cy="{SIZE / 2}" r="{r}" fill="{color}"/>'
        f"</svg>\n"
    )


def render(history: pathlib.Path, out_dir: pathlib.Path, window_days: int = 30) -> dict[str, str]:
    verdicts = {v.source: v.verdict for v in judge_all(load(history, window_days))}

    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for source in sorted(set(PROBES) | set(verdicts)):
        verdict = verdicts.get(source, "unknown")
        (out_dir / f"{source}.svg").write_text(
            dot(COLOR.get(verdict, COLOR["unknown"]), f"{source}: {verdict}"),
            encoding="utf-8",
        )
        written[source] = verdict

    # Fixed swatches for the README legend. They live here rather than as emoji
    # in the prose so the legend and the lights can never drift apart: one
    # COLOR map feeds both.
    for verdict, color in COLOR.items():
        (out_dir / f"_legend_{verdict}.svg").write_text(dot(color, verdict), encoding="utf-8")

    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history", type=pathlib.Path, required=True)
    ap.add_argument(
        "-o",
        "--out",
        type=pathlib.Path,
        default=pathlib.Path("dots"),
        help="directory to write <source>.svg into (default: dots/)",
    )
    ap.add_argument("--window-days", type=int, default=30)
    args = ap.parse_args(argv)

    written = render(args.history, args.out, args.window_days)

    tally: dict[str, int] = {}
    for verdict in written.values():
        tally[verdict] = tally.get(verdict, 0) + 1
    summary = ", ".join(f"{n} {k}" for k, n in sorted(tally.items(), key=lambda kv: -kv[1]))
    print(f"{len(written)} dots -> {args.out}/  ({summary})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""The README's status lights are static URLs, so nothing checks them at runtime.

Each light is an <img> pointing at a file the health workflow writes onto the
health-history branch. That decoupling is the whole point — the lights refresh
daily without a commit to main — but it means the two halves can drift apart
silently, and both failure modes are quiet in the worst way:

  - a probe with no README row      -> the source is watched but nothing shows it
  - a README row with no dot file   -> raw.githubusercontent 404s, and GitHub
                                       renders a broken-image icon, which reads
                                       as "this repo is abandoned"

Neither shows up in CI otherwise: the workflow is green, the markdown is valid,
and only a human looking at the rendered page would notice. So the wiring is
asserted here, offline and fast, where adding a probe and forgetting the row
fails immediately.
"""
from __future__ import annotations

import pathlib
import re
from datetime import datetime, timedelta, timezone

from scripts.health_panel import COLOR, PROBES, dot, render

ROOT = pathlib.Path(__file__).parent.parent
README = ROOT / "README.md"
HEALTH_DIR = ROOT / "tests" / "health"

# Matches the dot URLs the README embeds. Digits matter: `co2`.
_DOT_URL = re.compile(r"health-history/dots/([a-z0-9_]+)\.svg")


def _referenced() -> set[str]:
    return set(_DOT_URL.findall(README.read_text(encoding="utf-8")))


def _probe_names() -> set[str]:
    return {p.stem.removeprefix("test_") for p in HEALTH_DIR.glob("test_*.py")}


def test_probe_list_matches_the_probes_on_disk():
    """PROBES is hand-maintained so the script can run against a history file
    alone, with no test directory present. That freedom costs this assertion."""
    assert set(PROBES) == _probe_names()


def test_every_probe_has_a_light_in_the_readme():
    missing = _probe_names() - _referenced()
    assert not missing, (
        f"probed but no README row: {sorted(missing)} — "
        f"the source is monitored and nobody can see it"
    )


def test_every_readme_light_resolves_to_a_file_we_emit(tmp_path):
    """Guards against a typo'd URL, which renders as a broken image."""
    (tmp_path / "history.jsonl").write_text("", encoding="utf-8")
    render(tmp_path / "history.jsonl", tmp_path / "dots")

    emitted = {p.stem for p in (tmp_path / "dots").glob("*.svg")}
    dangling = _referenced() - emitted
    assert not dangling, f"README points at dots we never write: {sorted(dangling)}"


def test_legend_swatches_are_emitted(tmp_path):
    (tmp_path / "history.jsonl").write_text("", encoding="utf-8")
    render(tmp_path / "history.jsonl", tmp_path / "dots")

    for verdict in COLOR:
        assert (tmp_path / "dots" / f"_legend_{verdict}.svg").exists()


def test_sources_with_no_history_still_get_a_dot(tmp_path):
    """A 404 reads as neglect; grey reads as "no observations yet". Emit grey."""
    (tmp_path / "history.jsonl").write_text("", encoding="utf-8")
    written = render(tmp_path / "history.jsonl", tmp_path / "dots")

    assert set(written) == set(PROBES)
    assert set(written.values()) == {"unknown"}
    assert COLOR["unknown"] in (tmp_path / "dots" / "vedur.svg").read_text(encoding="utf-8")


def test_history_drives_the_colour(tmp_path):
    hist = tmp_path / "history.jsonl"
    # Relative dates: the verdict window is "now − 30 days", and hardcoded
    # timestamps age out — this test broke exactly that way in 2026-08 when
    # its July fixtures slid out of the window and vedur went 'unknown'.
    now = datetime.now(timezone.utc)
    hist.write_text(
        "\n".join(
            f'{{"ts": "{(now - timedelta(days=2 - day)).isoformat()}", '
            f'"source": "vedur", "status": "healthy"}}'
            for day in (0, 1, 2)  # today, yesterday, day before
        ),
        encoding="utf-8",
    )
    written = render(hist, tmp_path / "dots")

    assert written["vedur"] == "healthy"
    assert COLOR["healthy"] in (tmp_path / "dots" / "vedur.svg").read_text(encoding="utf-8")
    # Untouched sources stay grey rather than inheriting anything.
    assert written["natt"] == "unknown"


def test_dot_is_sanitiser_safe():
    """GitHub strips scripts from SVG and serves it through camo. Plain shapes only."""
    svg = dot(COLOR["healthy"], "vedur: healthy")
    assert "<script" not in svg and "onload" not in svg
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")

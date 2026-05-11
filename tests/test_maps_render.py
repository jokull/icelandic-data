"""Smoke tests: each map script writes a non-trivial PNG.

Skipped when the cache is empty (the cold path is exercised by the bench
harness, not the test suite).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from scripts.utils.cache import CONSTANTS_PATH, ROOT

REPORTS = ROOT / "reports"

MAPS = [
    ("grassland", "scripts/grassland_map.py", "reports/grassland-map.png"),
    ("grassland_prob", "scripts/grassland_probability_heatmap.py",
     "reports/grassland-probability-heatmap.png"),
    ("agricultural", "scripts/agricultural_land_map.py",
     "reports/agricultural-land-map.png"),
]


@pytest.fixture(scope="module", autouse=True)
def _require_cache():
    if not CONSTANTS_PATH.exists():
        pytest.skip(
            "Cache not built. Run: uv run python scripts/build_cache.py all")


@pytest.mark.parametrize("name,script,output", MAPS, ids=[m[0] for m in MAPS])
def test_map_renders(name: str, script: str, output: str) -> None:
    script_path = ROOT / script
    output_path = ROOT / output
    if not script_path.exists():
        pytest.skip(f"{script} not present in this branch")

    # If the agricultural-land source GeoJSON is missing, skip — fetching is
    # out-of-scope for the test suite (the bench harness covers cold runs).
    if name == "agricultural" and not (
            ROOT / "data" / "raw" / "natt" / "vistgerdir"
            / "L14.2__tun_og_akurlendi.geojson").exists():
        pytest.skip("agricultural source GeoJSON missing — run scripts/natt.py")

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, (
        f"{script} exited {result.returncode}\n"
        f"stdout: {result.stdout[-500:]}\n"
        f"stderr: {result.stderr[-1000:]}"
    )
    assert output_path.exists(), f"missing output {output_path}"
    img = Image.open(output_path)
    arr = np.array(img.convert("RGB"))
    assert arr.shape[0] > 1000 and arr.shape[1] > 1000, \
        f"output dims look wrong: {arr.shape}"
    assert arr.std() > 5.0, f"output PNG looks blank/uniform — std={arr.std():.1f}"

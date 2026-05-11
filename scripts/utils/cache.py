"""Derived-cache helper for map-construction scripts.

Three on-disk tiers live under ``data/cache/`` (gitignored, see ``.gitignore``):

- ``data/cache/constants.json``     — Iceland total area, bboxes, source SHA-256s,
                                       per-layer scalar stats. Built by
                                       ``scripts/build_cache.py constants``.
- ``data/cache/rasters/<name>.tif`` — LZW-compressed, ISN93 (EPSG:3057) projected
                                       GeoTIFFs derived from
                                       ``data/raw/lmi_hrl/*.tif``. Built by
                                       ``scripts/build_cache.py rasters``.
- ``data/cache/arrays/<name>.npy``  — opportunistic numpy memos written by render
                                       scripts on first run (e.g. decoded GRAVPI
                                       probability grid).

This module exposes thin readers; it never builds. Render scripts call:

    from scripts.utils.cache import iceland_constants, cached_raster, CacheMissingError

    try:
        K = iceland_constants()
    except CacheMissingError as e:
        print(e.hint, file=sys.stderr)
        ...
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "data" / "cache"
CONSTANTS_PATH = CACHE / "constants.json"
RASTERS_DIR = CACHE / "rasters"
ARRAYS_DIR = CACHE / "arrays"


class CacheMissingError(RuntimeError):
    """Raised when a cache entry is required but absent.

    The ``hint`` attribute always carries the exact CLI command that would
    rebuild the missing entry — render scripts should print that and exit
    or fall back gracefully.
    """

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message)
        self.hint = hint


def iceland_constants() -> dict:
    """Return the Tier 4 constants dict.

    Raises ``CacheMissingError`` if the cache hasn't been built. Callers may
    catch and fall back to recomputing — but the steady-state expectation is
    that this is a sub-millisecond JSON read.
    """
    if not CONSTANTS_PATH.exists():
        raise CacheMissingError(
            f"Missing {CONSTANTS_PATH.relative_to(ROOT)}",
            hint="Run: uv run python scripts/build_cache.py constants",
        )
    return json.loads(CONSTANTS_PATH.read_text(encoding="utf-8"))


def cached_raster(name: str) -> Path:
    """Path to a Tier 3 derived raster (e.g. ``"grassland_isn93"``)."""
    p = RASTERS_DIR / f"{name}.tif"
    if not p.exists():
        raise CacheMissingError(
            f"Missing {p.relative_to(ROOT)}",
            hint=f"Run: uv run python scripts/build_cache.py rasters --only {name}",
        )
    return p


def cached_array(name: str) -> Path:
    """Path to a Tier 5 numpy memo (e.g. ``"gravpi_prob_3057"``).

    Returns the path even if it doesn't exist — this tier is *opportunistic*,
    written by render scripts on first run. Use ``.exists()`` on the returned
    Path to decide whether to recompute.
    """
    ARRAYS_DIR.mkdir(parents=True, exist_ok=True)
    return ARRAYS_DIR / f"{name}.npy"


def ensure_cache(*, tier: int = 4) -> None:
    """Preflight check used at the top of refactored render scripts.

    ``tier=3`` requires the derived rasters too. Default ``tier=4`` only
    requires constants (most maps just need scalars, not the reprojected raster).
    """
    if tier >= 4 and not CONSTANTS_PATH.exists():
        raise CacheMissingError(
            "Cache is empty",
            hint="Run: uv run python scripts/build_cache.py all",
        )
    if tier >= 3 and not RASTERS_DIR.exists():
        raise CacheMissingError(
            "Derived raster cache is empty",
            hint="Run: uv run python scripts/build_cache.py rasters",
        )


def sha256_file(path: Path, *, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file — streamed so we don't blow up on the 826 MB TIFF."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()

"""Wall-clock + peak-memory benchmark harness for map-construction scripts.

Three modes:

- ``cold``      — wipes ``data/cache/`` AND ``data/raw/lmi_hrl/`` first
                  (full re-download path; expensive, run sparingly).
- ``warm-raw``  — wipes only ``data/cache/``; keeps the raw GeoTIFFs.
                  Measures the cost of rebuilding the derived cache + render.
- ``warm``      — keeps everything (steady-state developer experience).

Each map runs in a subprocess so memory peaks are measured cleanly. Results
land in stdout *and* are appended to ``data/cache/benchmarks.json`` with a
timestamp. When a previous ``warm`` baseline is present the stdout table
shows a delta column.

Usage::

    bench_maps.py run                       # warm mode, all maps
    bench_maps.py run --mode warm-raw
    bench_maps.py run --maps grassland,grassland_prob
    bench_maps.py run --mode cold --maps grassland   # use sparingly
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.cache import CACHE, ROOT  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

RAW_LMI_HRL = ROOT / "data" / "raw" / "lmi_hrl"
BENCHMARKS_PATH = CACHE / "benchmarks.json"

MAPS: dict[str, dict] = {
    "grassland": {
        "script": "scripts/grassland_map.py",
        "output": "reports/grassland-map.png",
    },
    "grassland_prob": {
        "script": "scripts/grassland_probability_heatmap.py",
        "output": "reports/grassland-probability-heatmap.png",
    },
    "agricultural": {
        "script": "scripts/agricultural_land_map.py",
        "output": "reports/agricultural-land-map.png",
    },
}

MODES = ("cold", "warm-raw", "warm")


# ── prep ─────────────────────────────────────────────────────────────────

def _wipe(p: Path) -> None:
    if p.exists():
        shutil.rmtree(p)


def _prepare_filesystem(mode: str) -> None:
    if mode == "cold":
        _wipe(CACHE)
        _wipe(RAW_LMI_HRL)
    elif mode == "warm-raw":
        _wipe(CACHE)
        # Keep RAW_LMI_HRL
    elif mode == "warm":
        pass
    else:
        raise SystemExit(f"unknown mode {mode!r}")


def _build_cache_if_needed() -> None:
    """For warm-raw and warm modes we want the derived cache present before
    rendering. (Cold mode also runs build_cache automatically once the source
    raster is back.) Skip silently if the cache build fails — the maps fall
    back to recomputing from source."""
    if not (CACHE / "constants.json").exists():
        print("  [bench] rebuilding cache ...", file=sys.stderr)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_cache.py"), "all"],
            cwd=str(ROOT), check=False,
        )


def _ensure_raw_for_cold() -> None:
    """Cold mode wipes the raw HRL TIFF — refetch it before timing the maps,
    so the per-map measurement excludes the (very long) download."""
    src = RAW_LMI_HRL / "grassland_20m.tif"
    if not src.exists():
        print("  [bench] cold mode: re-fetching grassland 20 m ...",
              file=sys.stderr)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "lmi_hrl.py"),
             "fetch", "grassland"],
            cwd=str(ROOT), check=True,
        )


# ── run one map ──────────────────────────────────────────────────────────

def _run_one(name: str, *, mode: str) -> dict:
    spec = MAPS[name]
    script = ROOT / spec["script"]
    output = ROOT / spec["output"]
    if not script.exists():
        return {"name": name, "skipped": "script absent"}

    # Best-effort peak-memory: psutil if available, else just wall time.
    try:
        import psutil   # type: ignore
        have_psutil = True
    except ImportError:
        have_psutil = False

    if output.exists():
        output.unlink()

    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    peak_rss_mb = 0.0
    if have_psutil:
        try:
            ps = psutil.Process(proc.pid)
            while proc.poll() is None:
                try:
                    rss = ps.memory_info().rss
                    for ch in ps.children(recursive=True):
                        try:
                            rss += ch.memory_info().rss
                        except psutil.Error:
                            pass
                    peak_rss_mb = max(peak_rss_mb, rss / 1e6)
                except psutil.Error:
                    break
                time.sleep(0.1)
        except psutil.Error:
            pass
    stdout, stderr = proc.communicate(timeout=900)
    dt = time.perf_counter() - t0

    out_size_mb = output.stat().st_size / 1e6 if output.exists() else 0.0
    return {
        "name": name,
        "mode": mode,
        "wall_seconds": round(dt, 2),
        "peak_rss_mb": round(peak_rss_mb, 1) if peak_rss_mb else None,
        "output": str(spec["output"]),
        "output_size_mb": round(out_size_mb, 2),
        "exit_code": proc.returncode,
        "stderr_tail": stderr[-500:] if proc.returncode else None,
    }


# ── reporting ────────────────────────────────────────────────────────────

def _load_history() -> list[dict]:
    if BENCHMARKS_PATH.exists():
        try:
            return json.loads(BENCHMARKS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return []


def _save_history(history: list[dict], record: dict) -> None:
    history.append(record)
    BENCHMARKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    BENCHMARKS_PATH.write_text(
        json.dumps(history, indent=2), encoding="utf-8")


def _last_warm_baseline(history: list[dict], name: str) -> float | None:
    for rec in reversed(history):
        if rec.get("mode") != "warm":
            continue
        for r in rec.get("results", []):
            if r.get("name") == name and r.get("exit_code") == 0:
                return r.get("wall_seconds")
    return None


def _print_table(record: dict, history: list[dict]) -> None:
    print()
    print(f"=== bench  mode={record['mode']}  ({record['built_at']}) ===")
    hdr = f"{'map':<18}  {'wall (s)':>9}  {'peak MB':>8}  {'png MB':>7}  {'Δ vs. last warm':>15}"
    print(hdr)
    print("-" * len(hdr))
    for r in record["results"]:
        if "skipped" in r:
            print(f"{r['name']:<18}  {'(skipped: ' + r['skipped'] + ')':>40}")
            continue
        prev = _last_warm_baseline(history[:-1], r["name"])
        if prev is not None and record["mode"] == "warm":
            delta = r["wall_seconds"] - prev
            delta_s = f"{delta:+.2f} s ({delta/prev*100:+.1f}%)"
        else:
            delta_s = "—"
        peak = f"{r['peak_rss_mb']:.0f}" if r.get("peak_rss_mb") else " —"
        png = f"{r['output_size_mb']:.2f}" if r.get("output_size_mb") else " —"
        print(f"{r['name']:<18}  {r['wall_seconds']:>9.2f}  "
              f"{peak:>8}  {png:>7}  {delta_s:>15}")


# ── CLI ──────────────────────────────────────────────────────────────────

def cmd_run(args: argparse.Namespace) -> None:
    if args.mode not in MODES:
        raise SystemExit(f"--mode must be one of {MODES}")

    targets = list(MAPS) if not args.maps else [m.strip() for m in args.maps.split(",")]
    for t in targets:
        if t not in MAPS:
            raise SystemExit(f"unknown map {t!r}; choices: {sorted(MAPS)}")

    print(f"  bench mode: {args.mode}", file=sys.stderr)
    _prepare_filesystem(args.mode)
    if args.mode == "cold":
        _ensure_raw_for_cold()
    _build_cache_if_needed()

    record = {
        "built_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "mode": args.mode,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "results": [],
    }
    for t in targets:
        print(f"  [bench] running {t} ...", file=sys.stderr)
        record["results"].append(_run_one(t, mode=args.mode))
    history = _load_history()
    _save_history(history, record)
    _print_table(record, history)


def cmd_history(_: argparse.Namespace) -> None:
    history = _load_history()
    if not history:
        print("(no benchmarks recorded yet)")
        return
    for rec in history[-5:]:
        _print_table(rec, history[:history.index(rec) + 1])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    r = sp.add_parser("run", help="run one bench cycle")
    r.add_argument("--mode", choices=MODES, default="warm",
                   help="cold | warm-raw | warm  (default: warm)")
    r.add_argument("--maps", help="comma-separated subset, e.g. grassland,grassland_prob")
    r.set_defaults(fn=cmd_run)

    h = sp.add_parser("history", help="print last 5 bench records")
    h.set_defaults(fn=cmd_history)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

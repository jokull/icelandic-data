"""Check (and repair) the local setup — runs on macOS, Linux and Windows.

    uv run python scripts/setup_check.py

Verifies the Python version, that the dependencies import, that the
`.claude/skills` link resolves to `.agents/skills` (git checks symlinks out as
plain text files on Windows, and GitHub ZIP downloads flatten them everywhere),
and whether the optional Playwright Chromium browser is installed.

Exit code is 0 when everything required is in place.
"""

from __future__ import annotations

import importlib
import os
import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_REAL = REPO_ROOT / ".agents" / "skills"
SKILLS_LINK = REPO_ROOT / ".claude" / "skills"
REQUIRED_MODULES = ["polars", "httpx", "duckdb", "openpyxl", "bs4", "typer", "iceaddr"]
OPTIONAL_MODULES = {
    "geopandas": "maps (kortagerð, grassland, traffic maps)",
    "rasterio": "raster maps (natt, lmi-hrl)",
    "playwright": "browser-driven scrapers (Power BI, Tableau)",
}

OK, WARN, FAIL = "ok  ", "warn", "FAIL"


def report(status: str, msg: str) -> None:
    print(f"[{status}] {msg}")


def check_python() -> bool:
    v = sys.version_info
    ok = v >= (3, 11)
    report(OK if ok else FAIL, f"Python {v.major}.{v.minor}.{v.micro} on {platform.system()} ({platform.machine()})")
    return ok


def check_modules() -> bool:
    ok = True
    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
            report(OK, f"import {name}")
        except Exception as e:  # noqa: BLE001
            ok = False
            report(FAIL, f"import {name}: {e} — run `uv sync`")
    for name, purpose in OPTIONAL_MODULES.items():
        try:
            importlib.import_module(name)
            report(OK, f"import {name} ({purpose})")
        except Exception as e:  # noqa: BLE001
            report(WARN, f"import {name} failed ({purpose}): {e}")
    return ok


def skills_link_resolves() -> bool:
    try:
        return (SKILLS_LINK / "hagstofan" / "SKILL.md").is_file()
    except OSError:
        return False


def repair_skills_link() -> bool:
    """Make .claude/skills point at .agents/skills. Returns True when it resolves afterwards."""
    if skills_link_resolves():
        report(OK, ".claude/skills -> .agents/skills resolves")
        return True
    if not SKILLS_REAL.is_dir():
        report(FAIL, f"{SKILLS_REAL} is missing — is this a complete checkout?")
        return False
    # A symlink checked out as a plain text file, a dangling link, or nothing at all.
    if SKILLS_LINK.is_symlink() or SKILLS_LINK.is_file():
        SKILLS_LINK.unlink()
    elif SKILLS_LINK.is_dir():
        # Real directory with no skills in it (e.g. an empty dir from a ZIP) — only remove if empty.
        try:
            SKILLS_LINK.rmdir()
        except OSError:
            report(FAIL, f"{SKILLS_LINK} is a non-empty directory; move it aside and re-run")
            return False
    SKILLS_LINK.parent.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            # A directory junction needs neither admin rights nor Developer Mode.
            import _winapi

            _winapi.CreateJunction(str(SKILLS_REAL), str(SKILLS_LINK))
            kind = "junction"
        else:
            os.symlink(Path("..") / ".agents" / "skills", SKILLS_LINK, target_is_directory=True)
            kind = "symlink"
    except OSError as e:
        report(FAIL, f"could not create .claude/skills link: {e}")
        return False
    if skills_link_resolves():
        report(OK, f"created .claude/skills {kind} -> .agents/skills")
        return True
    report(FAIL, ".claude/skills still does not resolve after repair")
    return False


def check_claude_md() -> bool:
    p = REPO_ROOT / "CLAUDE.md"
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        report(FAIL, "CLAUDE.md missing")
        return False
    if "@AGENTS.md" in text:
        report(OK, "CLAUDE.md imports AGENTS.md")
        return True
    report(WARN, "CLAUDE.md does not import AGENTS.md — Claude Code may see stale instructions")
    return True


def check_playwright() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        report(WARN, "playwright not importable — browser scrapers unavailable")
        return
    try:
        with sync_playwright() as p:
            path = Path(p.chromium.executable_path)
        if path.exists():
            report(OK, "Playwright Chromium installed")
        else:
            report(WARN, "Playwright Chromium not installed — run `uv run playwright install chromium` for Power BI / Tableau scrapers")
    except Exception as e:  # noqa: BLE001
        report(WARN, f"Playwright check failed: {e}")


def check_utf8_console() -> None:
    enc = (sys.stdout.encoding or "").lower()
    if os.name == "nt" and "utf" not in enc and os.environ.get("PYTHONUTF8") != "1":
        report(WARN, f"console encoding is {enc!r}; set PYTHONUTF8=1 so Icelandic characters print correctly (setup.ps1 does this)")
    else:
        report(OK, f"console encoding {enc or 'unknown'}")


def main() -> int:
    ok = check_python()
    ok &= check_modules()
    ok &= repair_skills_link()
    ok &= check_claude_md()
    check_playwright()
    check_utf8_console()
    print()
    print("Setup looks good." if ok else "Setup has problems — see FAIL lines above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

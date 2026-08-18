# Python Scripting Gold Standard — icelandic-data

How a script in this repo should be written. The goal is a consistent "how"
across ~50 sources: a reader should be able to open any `scripts/*.py` and
already know where things live, how it's invoked, and what it produces — while
each script stays as small and as dependency-light as its job allows.

Pragmatic over dogmatic: the rules below are the default, and every one of
them has a legitimate exception when the data demands it — but the exception
should be visible in a comment, not silent.

## a) Few dependencies

- **Standard library first**: `argparse`, `pathlib`, `csv`, `json`, `gzip`,
  `re` cover most CLI + I/O needs with zero installs.
- **Two project workhorses**: `polars` for all tabular data, `httpx` for all
  HTTP. That's it by default.
- **Domain-specific deps only on explicit need**, and heavy ones imported
  lazily inside the function that uses them (`playwright`, `docling`,
  `geopandas`, `pdfplumber`, `openpyxl`) so a quick CLI path never pays the
  import cost.
- Never `requests` (httpx is the standard). Never `pandas` (polars is the
  standard). New dependencies go in `pyproject.toml` and `uv sync --locked`
  must keep `uv.lock` in step — or CI fails.

## b) Entry point and CLI

- Every script has a `def main()` guarded by `if __name__ == "__main__"`.
- Use stdlib `argparse`. Subcommands via `add_parser(...)` + `set_defaults(func=...)`.
- `fetch` is the universal subcommand (download → tidy output). `list` appears
  when the source has a discoverable catalog (stations, datasets, dashboards).
  Single-purpose processors may have no subcommands, but they still get a real
  argparse main with options and `--help` derived from the module docstring.
- Bare `python scripts/x.py` (no args) must do the useful default thing — that
  is what AGENTS.md quick commands invoke.
- Exit non-zero on total failure; a partial failure prints what failed.
- `argparse.ArgumentParser(description=__doc__)` — one source of truth for help.

## c) HTTP hygiene

- `httpx` with an **explicit timeout** on every call — convention `60`;
  document a larger value when the payload is big.
- An identifying `User-Agent` string so upstreams can see who's asking.
- `raise_for_status()` and let errors bubble — a 404 or 5xx is information.
- Retry only connection-level errors (the health-probe `http` fixture does
  this); never retry a response that arrived.
- No `except Exception: pass`. A failed fetch is either raised, or printed
  loudly to stderr and accounted for — never silent, never turned into a `0`.

## d) Paths

- Anchor everything to the script: `ROOT = Path(__file__).resolve().parent.parent`,
  never cwd-relative `Path("data/...")` (breaks from any other directory).
- `RAW_DIR = ROOT / "data" / "raw" / "{source}"` — save downloads as-received.
- `PROCESSED_DIR = ROOT / "data" / "processed"` — tidy, long-format output.
- Tidy output never lands in `data/raw/`, and raw dumps never land in
  `data/processed/`. Both dirs are gitignored.

## e) Encoding

- `encoding="utf-8"` on every text `open()` / `write_text()`. Always.
- Decode exotic encodings explicitly and document why: UTF-16 JSON with BOM
  (httpx decodes it), iso-8859-1 legacy spreadsheets, `utf-8-sig` CSVs.
- After any fetch pipeline, verify Icelandic characters (þ, ð, æ, ö, ú)
  round-trip — a mojibake row is a data bug.

## f) Data

- polars, tidy long format (one row per observation), never wide spaghetti.
- Dates are `pl.Date` / `pl.Datetime`, not strings; numbers are numbers —
  no "1.234,5" strings, no comma-thousands leaking into doubles.
- Dedupe on the natural key with `keep="last"` (sources revise).
- Raw stays raw; transformations happen in the script, not by hand.

## g) Progress and failure visibility

- Print progress to stdout (`  {n} records fetched`, per-record in batches).
- Per-record crawls: `except` per record, print the skip reason, continue.
- Pipeline steps: raise. A summary line at the end states what was skipped,
  so a partially-missing output is never mistaken for a complete one.

## h) Idempotency

- Cache raw downloads; `--force` re-fetches.
- Don't re-download what a cache TTL says is fresh (24h for live sources,
  immutable forever for closed/historical ones).

## i) Skill docs — no template

Skills are **not** templated. No mandatory section list, no forced "Caveats"
heading. A `SKILL.md` is compressed to exactly what helps an agent navigate to
the data and the script:

- Frontmatter: `name:` matching the dir (lowercase ASCII, hyphens, no
  underscores/ð/æ) and `description:` ≤160 chars, front-loaded with the words
  someone would type (agency, Icelandic term) and what the skill covers.
- Body: what the source is, where the API/data lives, how to run the script,
  and the gotchas that actually bite — in whatever order and shape the source
  warrants. A section earns its place by preventing a mistake, not by
  convention.

The `description` is the whole discovery mechanism — both agents preload it,
and the combined budget is ~8,000 chars, so brevity is a hard constraint.

## j) Health probe

- `tests/health/test_{source}.py`, probing the **smallest stable contract**
  (status, content-type, required keys, a known identifier) — not the data.
- Use the `http` fixture; never write to `data/`.
- Staleness is `degraded_ok`, unreachable-vs-wrong is distinguished in the
  failure message (`f"{url} -> {status}"` / `type(exc).__name__`).
- Every probe is registered in `scripts/health_panel.py` PROBES (a test
  enforces probe↔PROBES 1:1), has a README row, and a quick command.

## k) Tests

- Offline unit tests (`tests/test_{source}.py`) for the parsing/extraction
  logic — the regex-heavy scripts especially. No network, no browser.
- The live health probe covers upstream; the unit tests cover *our* code.
- A script with non-trivial parsing and zero offline tests is a review blocker.

## l) Verify before you call it done

- `duckdb -c "SELECT * FROM 'data/processed/{output}' LIMIT 5"` — dates parse,
  numbers are numeric, Icelandic chars render.
- `uv run pytest -m "not slow"` green, and still offline.
- The health probe passes against the live source.

## Checklist

- [ ] `main()` + argparse, `--help` works, bare run does the useful default
- [ ] httpx `timeout=60` + identifying UA; no bare except
- [ ] `__file__`-anchored paths; raw→`data/raw/{source}/`, tidy→`data/processed/`
- [ ] `encoding="utf-8"` on every text write; Icelandic verified
- [ ] polars, tidy long, typed dates, natural-key dedupe
- [ ] progress prints; skips accounted for in the summary
- [ ] compressed `SKILL.md` (no template) with `description` ≤160
- [ ] health probe registered (PROBES / README / quick command)
- [ ] offline unit tests for parsing logic
- [ ] duckdb spot-check + full fast suite green

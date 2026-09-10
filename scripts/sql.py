"""Run a DuckDB query against local files — a portable stand-in for the `duckdb` CLI.

    uv run python scripts/sql.py "SELECT * FROM 'data/processed/*.csv' LIMIT 10"
    uv run python scripts/sql.py --csv "SELECT ..." > out.csv
    echo "SELECT 1" | uv run python scripts/sql.py

Uses the `duckdb` Python package (a dependency of this project), so no separate
DuckDB binary or Homebrew is needed on any platform. Paths in the query are
resolved relative to the repository root, so the examples in AGENTS.md and the
skills work from any working directory.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("query", nargs="?", help="SQL to run (reads stdin if omitted)")
    ap.add_argument("--csv", action="store_true", help="print CSV instead of a table")
    ap.add_argument("--json", action="store_true", help="print one JSON object per row")
    args = ap.parse_args(argv)

    query = args.query if args.query is not None else sys.stdin.read()
    if not query.strip():
        ap.error("no query given")

    os.chdir(REPO_ROOT)
    con = duckdb.connect()
    rel = con.sql(query)
    if rel is None:  # statements with no result set (CREATE, COPY, ...)
        return 0
    if args.csv:
        import csv

        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(newline="")  # csv writes its own line endings
        w = csv.writer(sys.stdout, lineterminator="\n")
        w.writerow(rel.columns)
        w.writerows(rel.fetchall())
        return 0
    if args.json:
        import json

        cols = rel.columns
        for row in rel.fetchall():
            print(json.dumps(dict(zip(cols, row)), ensure_ascii=False, default=str))
        return 0
    rel.show(max_rows=1000, max_width=200)
    return 0


if __name__ == "__main__":
    sys.exit(main())

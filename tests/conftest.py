"""Shared pytest fixtures for icelandic-data tests.

Makes scripts/ importable as a package so tests can import modules like
`scripts.tekjusagan` without shell gymnastics.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

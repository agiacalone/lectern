"""Suite version matrix: installed components must satisfy SUITE.md (absent => skip)."""
from pathlib import Path
import pytest
from lectern import suite_check as sc

pytestmark = pytest.mark.suite

SUITE_MD = Path(__file__).resolve().parents[2] / "SUITE.md"


def test_suite_md_parses():
    m = sc.load_matrix(SUITE_MD)
    assert "components" in m and "lectern" in m["components"]


def test_installed_components_satisfy_matrix():
    matrix = sc.load_matrix(SUITE_MD)
    results = sc.check(matrix)
    mismatches = [r for r in results if not r.ok and not r.skipped]
    assert not mismatches, f"version mismatch vs SUITE.md: {mismatches}"

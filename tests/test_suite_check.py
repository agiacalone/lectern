# tests/test_suite_check.py
from pathlib import Path
import textwrap
import pytest
from lectern import suite_check as sc

SUITE_MD = textwrap.dedent('''\
    # LMS Suite
    ```yaml
    suite: "LMS Suite"
    release: "v0.1.0-rc1"
    components:
      lectern:     ">=0.5.0,<0.6"
      scriptorium: ">=0.1.0,<0.2"
      oracle:      ">=0.3.0,<0.4"
    seam_contracts:
      reading_list: 1
      autograde: 1
      question_bank: 0
    ```
    ''')

def test_load_matrix(tmp_path):
    p = tmp_path / "SUITE.md"; p.write_text(SUITE_MD)
    m = sc.load_matrix(p)
    assert m["components"]["lectern"] == ">=0.5.0,<0.6"
    assert m["seam_contracts"]["question_bank"] == 0

@pytest.mark.parametrize("ver,spec,ok", [
    ("0.5.0", ">=0.5.0,<0.6", True),
    ("0.5.9", ">=0.5.0,<0.6", True),
    ("0.6.0", ">=0.5.0,<0.6", False),
    ("0.4.9", ">=0.5.0,<0.6", False),
    ("0.3.2", ">=0.3.0,<0.4", True),
])
def test_in_range(ver, spec, ok):
    assert sc.in_range(ver, spec) is ok

def test_resolve_scriptorium_from_package_json(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"scriptorium","version":"0.1.0"}')
    assert sc.resolve_version("scriptorium", root=tmp_path) == "0.1.0"

def test_resolve_absent_component_returns_none(tmp_path):
    assert sc.resolve_version("oracle", root=tmp_path / "nope") is None

def test_check_flags_out_of_range(tmp_path):
    p = tmp_path / "SUITE.md"; p.write_text(SUITE_MD)
    matrix = sc.load_matrix(p)
    # scriptorium present but too new; oracle absent (skipped); lectern present in-range
    scrip = tmp_path / "scrip"; scrip.mkdir()
    (scrip / "package.json").write_text('{"version":"0.2.5"}')
    results = sc.check(matrix, roots={"scriptorium": scrip, "oracle": tmp_path / "absent"})
    by = {r.component: r for r in results}
    assert by["scriptorium"].ok is False and by["scriptorium"].skipped is False
    assert by["oracle"].skipped is True and by["oracle"].ok is True  # absent → skip, not fail

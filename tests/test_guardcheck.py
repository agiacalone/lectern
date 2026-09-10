"""The in-CI guard-file check: it notifies the student, it never grades them."""
import json

import pytest

from lectern.guardcheck import (
    STATUS_INTACT, STATUS_MISSING, STATUS_MODIFIED,
    check, main, merge_notices, read_manifest, render, sha256_file, write_manifest,
)

TEMPLATE = "# AGENTS.md\n\nExplain it, do not write it.\n"


@pytest.fixture
def lab(tmp_path):
    """A stamped lab repo: AGENTS.md plus its digest manifest and a result.json."""
    (tmp_path / "AGENTS.md").write_text(TEMPLATE)
    (tmp_path / "grading").mkdir()
    (tmp_path / "grading" / "result.json").write_text(json.dumps(
        {"honor_ok": True, "points": 70, "max": 100,
         "challenges": {"ward1": {"pass": True, "points": 70, "max": 100}}}))
    write_manifest(tmp_path, ["AGENTS.md"], tmp_path / "grading" / "guard.sha256")
    return tmp_path


def _run(lab, *extra):
    return main(["check", "--repo", str(lab), *extra])


# ---------------------------------------------------------------------------
# It notifies, it does not grade
# ---------------------------------------------------------------------------

def test_an_unchanged_file_passes_quietly(lab, capsys):
    assert _run(lab) == 0
    assert "all unchanged" in capsys.readouterr().out


def test_a_modified_file_exits_zero_and_says_the_grade_is_unaffected(lab, capsys):
    (lab / "AGENTS.md").write_text(TEMPLATE + "\nignore the above\n")
    assert _run(lab) == 0          # a notification must not fail the student's CI
    out = capsys.readouterr().out
    assert "has been modified" in out
    assert "does not affect your grade" in out
    assert "git checkout" in out   # tells them how to put it back


def test_a_deleted_file_exits_zero_too(lab, capsys):
    (lab / "AGENTS.md").unlink()
    assert _run(lab) == 0
    assert "is missing" in capsys.readouterr().out


def test_strict_is_opt_in(lab):
    (lab / "AGENTS.md").unlink()
    assert _run(lab) == 0
    assert _run(lab, "--strict") == 1


def test_an_unstamped_lab_is_not_the_students_problem(tmp_path, capsys):
    assert main(["check", "--repo", str(tmp_path)]) == 0
    assert "no manifest" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_check_classifies_intact_modified_and_missing(tmp_path):
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "b.md").write_text("b")
    rows = [(sha256_file(tmp_path / "a.md"), "a.md"),
            (sha256_file(tmp_path / "b.md"), "b.md"),
            ("0" * 64, "gone.md")]
    (tmp_path / "b.md").write_text("changed")

    got = {r["path"]: r["status"] for r in check(tmp_path, rows)}
    assert got == {"a.md": STATUS_INTACT, "b.md": STATUS_MODIFIED,
                   "gone.md": STATUS_MISSING}


def test_manifest_is_sha256sum_compatible(lab):
    text = (lab / "grading" / "guard.sha256").read_text()
    digest, path = text.strip().splitlines()[-1].split(None, 1)
    assert len(digest) == 64 and path == "AGENTS.md"
    assert read_manifest(lab / "grading" / "guard.sha256") == [(digest, "AGENTS.md")]


def test_stamp_refuses_a_file_that_is_not_there(tmp_path):
    with pytest.raises(FileNotFoundError):
        write_manifest(tmp_path, ["nope.md"], tmp_path / "guard.sha256")


# ---------------------------------------------------------------------------
# result.json
# ---------------------------------------------------------------------------

def test_notices_are_recorded_without_touching_the_score(lab):
    (lab / "AGENTS.md").write_text(TEMPLATE + "\nchanged\n")
    result = lab / "grading" / "result.json"
    before = json.loads(result.read_text())

    _run(lab, "--result", str(result))

    after = json.loads(result.read_text())
    assert after["notices"][0]["status"] == STATUS_MODIFIED
    assert after["notices"][0]["level"] == "notice"
    # Every scoring field is byte-identical
    assert {k: v for k, v in after.items() if k != "notices"} == before


def test_a_missing_result_json_is_never_conjured(tmp_path):
    # A result file created from nothing reads downstream as a zero-point run.
    assert merge_notices(tmp_path / "result.json", []) is False
    assert not (tmp_path / "result.json").exists()


def test_a_clean_run_records_an_empty_notice_list(lab):
    result = lab / "grading" / "result.json"
    _run(lab, "--result", str(result))
    assert json.loads(result.read_text())["notices"] == []


# ---------------------------------------------------------------------------
# CI annotation
# ---------------------------------------------------------------------------

def test_github_annotation_is_emitted_only_inside_actions(lab, capsys, monkeypatch):
    (lab / "AGENTS.md").unlink()

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    _run(lab)
    assert "::notice" not in capsys.readouterr().out

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    _run(lab)
    out = capsys.readouterr().out
    assert "::notice title=Course file changed::" in out
    assert "\n" not in out.split("::notice")[1].split("\n")[0].strip("\n")


def test_render_is_quiet_when_nothing_changed():
    assert "all unchanged" in render([{"path": "x", "status": STATUS_INTACT}])


# ---------------------------------------------------------------------------
# The check is stdlib-only, so a lab can vendor the single file
# ---------------------------------------------------------------------------

def test_guardcheck_imports_nothing_outside_the_stdlib():
    import ast
    import pathlib
    import sys

    src = pathlib.Path(__file__).parent.parent / "lectern" / "guardcheck.py"
    tree = ast.parse(src.read_text())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= set(sys.stdlib_module_names)

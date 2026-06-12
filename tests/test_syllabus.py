import subprocess, pathlib, shutil, pytest
from lectern.syllabus import stamp
from lectern.syllabus_serial import compute_serial

needs_pandoc = pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")


def _git_repo(tmp_path, readme):
    r = tmp_path / "cecs-378-su26-01-syllabus-10660"; r.mkdir(parents=True, exist_ok=True)
    (r / "README.md").write_text(readme)
    subprocess.run(["git","init","-q"], cwd=r, check=True)
    subprocess.run(["git","add","-A"], cwd=r, check=True)
    subprocess.run(["git","-c","user.email=t@t","-c","user.name=t","commit","-qm","i"], cwd=r, check=True)
    return r


# Task 2: stamp tests

def test_stamp_injects_serial_and_footer(tmp_path):
    vault = tmp_path / "vault"; (vault / "notes").mkdir(parents=True)
    (vault / "notes" / "syllabus-serial-register.md").write_text("# Syllabus Serial Register\n")
    r = _git_repo(tmp_path, "---\nserial: OLD\n---\n# Syllabus\nbody\n")
    serial = stamp(r, vault, today="2026-06-09")
    text = (r / "README.md").read_text()
    assert f"serial: {serial}" in text
    assert f"*Syllabus version {serial} · 2026-06-09*" in text
    assert serial != "OLD" and len(serial) == 8

def test_stamp_idempotent_on_unchanged_tree(tmp_path):
    vault = tmp_path / "vault"; (vault / "notes").mkdir(parents=True)
    (vault / "notes" / "syllabus-serial-register.md").write_text("# Syllabus Serial Register\n")
    r = _git_repo(tmp_path, "---\nserial: X\n---\nbody\n")
    s1 = stamp(r, vault, today="2026-06-09")
    # committing the stamped state, re-stamp → same serial (strip makes it stable)
    subprocess.run(["git","add","-A"], cwd=r, check=True)
    subprocess.run(["git","-c","user.email=t@t","-c","user.name=t","commit","-qm","stamp"], cwd=r, check=True)
    s2 = stamp(r, vault, today="2026-06-09")
    assert s1 == s2


# Task 3: register append test

def test_register_appends_one_row_per_serial(tmp_path):
    vault = tmp_path / "vault"; (vault / "notes").mkdir(parents=True)
    reg = vault / "notes" / "syllabus-serial-register.md"
    reg.write_text("# Syllabus Serial Register\n")
    r = _git_repo(tmp_path, "---\nserial: X\n---\nbody\n")
    serial = stamp(r, vault, today="2026-06-09")
    text = reg.read_text()
    assert "## Live (Su26 forward)" in text
    assert f"| 378 | 01 | su26 | 10660 | {serial} | 2026-06-09 |" in text
    # idempotent on serial: stamp same tree again → still one row
    subprocess.run(["git","add","-A"], cwd=r, check=True)
    subprocess.run(["git","-c","user.email=t@t","-c","user.name=t","commit","-qm","s"], cwd=r, check=True)
    stamp(r, vault, today="2026-06-09")
    assert reg.read_text().count(f"| {serial} |") == 1


# Task 4: build test

@needs_pandoc
def test_build_emits_html_with_serial_footer(tmp_path):
    vault = tmp_path / "vault"; (vault / "notes").mkdir(parents=True)
    (vault / "notes" / "syllabus-serial-register.md").write_text("# R\n")
    r = _git_repo(tmp_path, "---\nserial: X\n---\n# Syllabus\n\n## Policies\nbody\n")
    serial = stamp(r, vault, today="2026-06-09")
    from lectern.syllabus import build
    build(r)
    html = (r / "syllabus.html").read_text()
    canvas = (r / "syllabus_canvas.html").read_text()
    assert serial in html and "Serial" in html
    assert "<style" not in canvas and "style=" in canvas   # Canvas-safe: inline only


# Task 5: CLI test

def test_cli_stamp_then_build(tmp_path, monkeypatch):
    vault = tmp_path / "vault"; (vault / "notes").mkdir(parents=True)
    (vault / "notes" / "syllabus-serial-register.md").write_text("# R\n")
    r = _git_repo(tmp_path, "---\nserial: X\n---\n# S\nbody\n")
    from lectern.syllabus import main
    assert main(["stamp", str(r), "--vault-root", str(vault), "--date", "2026-06-09"]) == 0
    assert "serial:" in (r / "README.md").read_text()

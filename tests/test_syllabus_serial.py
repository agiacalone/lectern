import subprocess, pathlib
from lectern.syllabus_serial import compute_serial, primary_md

def _git_repo(tmp_path, files: dict) -> pathlib.Path:
    r = tmp_path / "repo"; r.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (r / name).write_text(content)
    subprocess.run(["git", "init", "-q"], cwd=r, check=True)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=r, check=True)
    return r

def test_serial_is_deterministic_8hex(tmp_path):
    r = _git_repo(tmp_path, {"README.md": "---\nserial: AAAAAAAA\n---\n# Syllabus\nbody\n"})
    s1 = compute_serial(r); s2 = compute_serial(r)
    assert s1 == s2 and len(s1) == 8 and s1 == s1.upper()

def test_serial_ignores_its_own_serial_line(tmp_path):
    r1 = _git_repo(tmp_path / "a", {"README.md": "---\nserial: AAAAAAAA\n---\nbody\n"})
    r2 = _git_repo(tmp_path / "b", {"README.md": "---\nserial: ZZZZZZZZ\n---\nbody\n"})
    assert compute_serial(r1) == compute_serial(r2)   # serial line stripped before hashing

def test_serial_changes_on_body_edit(tmp_path):
    r1 = _git_repo(tmp_path / "a", {"README.md": "---\nserial: X\n---\nbody one\n"})
    r2 = _git_repo(tmp_path / "b", {"README.md": "---\nserial: X\n---\nbody TWO\n"})
    assert compute_serial(r1) != compute_serial(r2)

def test_primary_md_prefers_syllabus_then_readme(tmp_path):
    r = _git_repo(tmp_path, {"README.md": "x", "syllabus.md": "y"})
    assert primary_md(r) == "syllabus.md"

import textwrap, yaml
from pathlib import Path
from lectern.term_create import main as create_main
from lectern.vault_notes import split_frontmatter

SPEC = textwrap.dedent('''\
    term: fa26
    term-name: Fall 2026
    year: 2026
    semester-code: fa
    instructor: Anthony Giacalone
    start: 2026-08-24
    end: 2026-12-09
    finals-week-start: 2026-12-14
    finals-week-end: 2026-12-18
    grade-submission-deadline: 2026-12-23
    sections:
      - course: CECS 326
        section: "01"
        class-number: 1116
        room: HC-120
        meets: "TuTh 12:30-13:45"
        enrolled: 45
        final-exam-date: 2026-12-15
      - course: CECS 478
        section: "04"
        class-number: 12548
        room: ECS-405
        meets: "MW 17:00-18:15"
        enrolled: 15
        final-exam-date: 2026-12-14
''')

def _vault(tmp_path):
    V = tmp_path / "vault"
    (V / "templates").mkdir(parents=True)
    (V / "classes" / "326").mkdir(parents=True)
    (V / "classes" / "378-478").mkdir(parents=True)
    (V / "notes").mkdir(parents=True)
    # minimal templates carrying the frontmatter keys create() injects into
    (V / "templates" / "semester-note.md").write_text(
        "---\ntype: semester-note\nterm: \"{{term}}\"\nterm-name: \"{{term-name}}\"\n"
        "year: {{year}}\nsemester-code: \"{{semester-code}}\"\nsection-count: 0\ncourses: []\n"
        "total-enrolled: 0\nstart: \nend: \nfinals-week-start: \nfinals-week-end: \n"
        "grade-submission-deadline: \nstatus: in-progress\n---\n# {{term-name}}\n")
    (V / "templates" / "class-note.md").write_text(
        "---\ntype: class-note\ncourse: \"{{course}}\"\ncourse-num: {{course-num}}\n"
        "section: \"{{section}}\"\nterm: \"{{term}}\"\nterm-name: \"{{term-name}}\"\n"
        "class-number: {{class-number}}\narchive: archives/{{term}}-{{section}}/\n"
        "status: in-progress\nheadcount:\n  enrolled: 0\n  completed: 0\n  withdrew: 0\n"
        "dfw-rate: 0\nschedule:\n  meets: null\n  room: null\n  final-exam-date: null\n---\n"
        "# {{course}} §{{section}}\n")
    (V / "notes" / "MOC-cecs-326.md").write_text(
        "---\ntype: moc\n---\n# CECS 326\n## ☷ Sections taught\n\n## ▲ Labs\n")
    (V / "classes" / "fa26.spec.yaml").write_text(SPEC)
    return V

def test_create_materializes_everything(tmp_path):
    V = _vault(tmp_path)
    assert create_main(["--term", "fa26", "--vault-root", str(V)]) == 0
    # semester note
    sem = (V / "classes" / "fa26.md").read_text()
    fm, _ = split_frontmatter(sem)
    assert fm["section-count"] == 2
    assert sorted(fm["courses"]) == ["CECS 326", "CECS 478"]
    assert str(fm["grade-submission-deadline"]) == "2026-12-23"
    # class notes at right paths with injected enrolled + schedule
    c326 = (V / "classes" / "326" / "326-01-fa26.md").read_text()
    fmc, _ = split_frontmatter(c326)
    assert fmc["headcount"]["enrolled"] == 45
    assert fmc["schedule"]["room"] == "HC-120"
    assert fmc["class-number"] == 1116
    assert (V / "classes" / "378-478" / "478-04-fa26.md").exists()
    # manifest skeletons
    man = yaml.safe_load((V / "classes" / "326" / "archives" / "fa26-01" / "manifest.yaml").read_text())
    assert man["headcount"]["enrolled"] == 45
    assert str(man["class_number"]) == "1116"
    # MOC wiring (326 has a MOC; 378-478 MOC absent -> skipped silently)
    moc = (V / "notes" / "MOC-cecs-326.md").read_text()
    assert "326-01-fa26" in moc

def test_create_idempotent(tmp_path):
    V = _vault(tmp_path)
    assert create_main(["--term", "fa26", "--vault-root", str(V)]) == 0
    before = (V / "classes" / "326" / "326-01-fa26.md").read_text()
    # second run must not duplicate or alter existing files
    assert create_main(["--term", "fa26", "--vault-root", str(V)]) == 0
    after = (V / "classes" / "326" / "326-01-fa26.md").read_text()
    assert before == after
    moc = (V / "notes" / "MOC-cecs-326.md").read_text()
    assert moc.count("326-01-fa26") == 1   # no duplicate MOC link

def test_init_writes_stub_and_refuses_overwrite(tmp_path):
    V = _vault(tmp_path)
    (V / "classes" / "fa26.spec.yaml").unlink()
    assert create_main(["--term", "fa26", "--init", "--vault-root", str(V)]) == 0
    assert (V / "classes" / "fa26.spec.yaml").exists()
    assert create_main(["--term", "fa26", "--init", "--vault-root", str(V)]) == 1  # refuse

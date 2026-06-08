import pytest, textwrap
from pathlib import Path
from lectern.term_spec import load_term_spec, stub_spec_text, TermSpecError

VALID = textwrap.dedent('''\
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

def _w(p, s): p.write_text(s); return p

def test_load_valid(tmp_path):
    spec = load_term_spec(_w(tmp_path / "fa26.spec.yaml", VALID))
    assert spec["term"] == "fa26"
    assert len(spec["sections"]) == 2
    # course-dir derived per section
    assert spec["sections"][0]["course-dir"] == "326"
    assert spec["sections"][1]["course-dir"] == "378-478"

def test_missing_required_key_raises(tmp_path):
    bad = VALID.replace("term: fa26\n", "")
    with pytest.raises(TermSpecError):
        load_term_spec(_w(tmp_path / "b.yaml", bad))

def test_duplicate_section_raises(tmp_path):
    # Append a second copy of the CECS 326 §01 section. (Indentation kept
    # literal — textwrap.dedent here would strip the list-item indent and
    # corrupt the YAML, masking the duplicate-detection path under test.)
    dup = VALID + (
        '  - course: CECS 326\n'
        '    section: "01"\n'
        '    class-number: 1116\n'
        '    room: x\n'
        '    meets: y\n'
        '    enrolled: 1\n'
        '    final-exam-date: 2026-12-15\n'
    )
    with pytest.raises(TermSpecError):
        load_term_spec(_w(tmp_path / "d.yaml", dup))

def test_stub_spec_text_is_loadable(tmp_path):
    p = _w(tmp_path / "s.yaml", stub_spec_text("su26"))
    # stub has the term filled and at least one example section; must validate
    spec = load_term_spec(p)
    assert spec["term"] == "su26"

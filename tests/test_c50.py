import textwrap
from pathlib import Path

import pytest

from lectern import c50

SPEC_YAML = textwrap.dedent("""\
    term: fa26
    term-name: Fall 2026
    year: 2026
    semester-code: fa
    instructor: Anthony Giacalone
    start: 2026-08-24
    end: 2026-12-11
    finals-week-start: 2026-12-14
    finals-week-end: 2026-12-19
    grade-submission-deadline: 2026-12-24
    sections:
      - course: CECS 378
        section: "01"
        class-number: 4785
        room: VEC-331
        meets: "TuTh 11:00-12:15"
        enrolled: 35
        final-exam-date: 2026-12-17
      - course: CECS 326
        section: "01"
        class-number: 1131
        room: DESN-112
        meets: "TuTh 17:30-18:45"
        enrolled: 60
        final-exam-date: 2026-12-15
      - course: CECS 326
        section: "03"
        class-number: 10674
        room: DESN-112
        meets: "TuTh 15:30-16:45"
        enrolled: 69
        final-exam-date: 2026-12-15
""")

LAB_INDEX = textwrap.dedent("""\
    ---
    type: lab-index
    title: "CECS 326 — Lab 1 — Threads"
    course: "CECS 326"
    course-num: 326
    lab-number: 1
    lab-slug: threads
    gradebook-column: "Lab 1 - Threads"
    github-template: cecs-326-reading-processes_and_threads
    github-template-url: https://github.com/agiacalone/cecs-326-reading-processes_and_threads
    points: 20
    ---

    # CECS 326 — Lab 1 — Threads
""")

SCHEMA_YAML = textwrap.dedent("""\
    course: CECS 326
    term_default: fa26
    columns:
      - canvas_title: "Lab 1 - Threads"
        short_name: lab1
        title: "Lab 1 — Threads"
        points: 60
        group: assignments
""")

CLASS_NOTE = textwrap.dedent("""\
    ---
    type: class-note
    course: CECS 326
    section: "01"
    term: fa26
    github-classroom:
      id: null
      url: null
    updated: 2026-08-24T17:05:00-07:00
    ---

    # CECS 326 §01
""")


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / "classes" / "semesters").mkdir(parents=True)
    (root / "classes" / "semesters" / "fa26.spec.yaml").write_text(SPEC_YAML)

    labs = root / "classes" / "326" / "labs" / "threads"
    labs.mkdir(parents=True)
    (labs / "index.md").write_text(LAB_INDEX)
    (root / "classes" / "326" / "gradebook-schema.yaml").write_text(SCHEMA_YAML)
    (root / "classes" / "326" / "326-01-fa26.md").write_text(CLASS_NOTE)
    return root


# ── derivation ───────────────────────────────────────────────────────────────


def test_classroom_name_is_derived_not_typed():
    assert c50.classroom_name("CECS 326", "fa26", "01") == "cecs-326-fa26-01"
    assert c50.classroom_name("CECS 378", "fa26", "03") == "cecs-378-fa26-03"


@pytest.mark.parametrize(
    "number,lab_slug,expected",
    [
        (1, "threads", "lab-01-threads"),
        (1, "378-symmetric_cryptography", "lab-01-symmetric-cryptography"),
        (2, "concurrent_processing", "lab-02-concurrent-processing"),
        (10, "threads", "lab-10-threads"),
    ],
)
def test_assignment_slug_strips_course_prefix_and_underscores(number, lab_slug, expected):
    assert c50.derive_assignment_slug(number, lab_slug) == expected


def test_assignment_slug_rejects_an_unusable_result():
    with pytest.raises(c50.C50Error):
        c50.derive_assignment_slug(1, "Threads With Spaces")


# ── vault resolution ─────────────────────────────────────────────────────────


def test_find_lab_reads_the_index_note(vault):
    lab = c50.find_lab(vault, "CECS 326", 1)
    assert lab.slug == "threads"
    assert lab.assignment_slug == "lab-01-threads"
    assert lab.template == "agiacalone/cecs-326-reading-processes_and_threads"


def test_gradebook_schema_outranks_the_lab_notes_stale_points(vault):
    """The schema is rewritten each term; the lab note is authored once."""
    lab = c50.find_lab(vault, "CECS 326", 1)
    assert lab.points == 60
    assert lab.canvas_column == "Lab 1 - Threads"


def test_a_c50_slug_override_in_the_note_wins(vault):
    index = vault / "classes" / "326" / "labs" / "threads" / "index.md"
    index.write_text(index.read_text().replace(
        "lab-slug: threads", "lab-slug: threads\nc50-slug: lab-01-thread-questions"))
    assert c50.find_lab(vault, "CECS 326", 1).assignment_slug == "lab-01-thread-questions"


def test_find_lab_is_explicit_when_no_note_matches(vault):
    with pytest.raises(c50.C50Error, match="no lab-index note"):
        c50.find_lab(vault, "CECS 326", 7)


def test_find_lab_refuses_an_ambiguous_match(vault):
    dupe = vault / "classes" / "326" / "labs" / "threads-again"
    dupe.mkdir()
    (dupe / "index.md").write_text(LAB_INDEX)
    with pytest.raises(c50.C50Error, match="more than one note"):
        c50.find_lab(vault, "CECS 326", 1)


def test_template_owner_comes_from_the_url_when_the_name_is_bare(vault):
    assert c50.find_lab(vault, "CECS 326", 1).template.startswith("agiacalone/")


def test_a_bare_template_with_no_url_is_an_error(vault):
    index = vault / "classes" / "326" / "labs" / "threads" / "index.md"
    index.write_text(
        index.read_text().replace(
            "github-template-url: https://github.com/agiacalone/cecs-326-reading-processes_and_threads",
            "github-template-url: null",
        )
    )
    with pytest.raises(c50.C50Error, match="no owner"):
        c50.find_lab(vault, "CECS 326", 1)


def test_sections_for_filters_by_course_then_section(vault):
    from lectern.term_spec import load_term_spec

    spec = load_term_spec(c50.spec_path(vault, "fa26"))
    assert len(c50.sections_for(spec, "CECS 326", None)) == 2
    assert len(c50.sections_for(spec, "CECS 326", "03")) == 1
    assert len(c50.sections_for(spec, None, None)) == 3
    with pytest.raises(c50.C50Error):
        c50.sections_for(spec, "CECS 999", None)


def test_spec_path_is_explicit_when_the_term_has_no_spec(vault):
    with pytest.raises(c50.C50Error, match="no term-spec"):
        c50.spec_path(vault, "sp99")


# ── write-back ───────────────────────────────────────────────────────────────


def test_write_back_records_the_short_name_as_the_binding(vault):
    note = vault / "classes" / "326" / "326-01-fa26.md"
    assert c50.write_back(note, "Giacalone-CECS", "cecs-326-fa26-01", dry_run=False)
    text = note.read_text()
    assert "id: cecs-326-fa26-01" in text
    assert "classroom50/tree/main/cecs-326-fa26-01" in text
    assert "# CECS 326 §01" in text  # body survives


def test_write_back_is_idempotent(vault):
    note = vault / "classes" / "326" / "326-01-fa26.md"
    c50.write_back(note, "Giacalone-CECS", "cecs-326-fa26-01", dry_run=False)
    assert not c50.write_back(note, "Giacalone-CECS", "cecs-326-fa26-01", dry_run=False)


def test_write_back_leaves_the_file_alone_on_a_dry_run(vault):
    note = vault / "classes" / "326" / "326-01-fa26.md"
    before = note.read_text()
    assert c50.write_back(note, "Giacalone-CECS", "cecs-326-fa26-01", dry_run=True)
    assert note.read_text() == before


# ── announcement ─────────────────────────────────────────────────────────────


def test_announcement_carries_the_exact_accept_command(vault):
    lab = c50.find_lab(vault, "CECS 326", 1)
    sec = {"course": "CECS 326", "section": "01"}
    text = c50.announcement(
        "Giacalone-CECS", "cecs-326-fa26-01", lab, sec, "2026-09-24T23:59:00-07:00")
    assert (
        "gh student accept Giacalone-CECS cecs-326-fa26-01 lab-01-threads" in text
    )
    assert "60 points" in text
    assert "Thursday, September 24 at 11:59 PM" in text


def test_announcement_survives_a_missing_due_date(vault):
    lab = c50.find_lab(vault, "CECS 326", 1)
    sec = {"course": "CECS 326", "section": "01"}
    text = c50.announcement("Giacalone-CECS", "cecs-326-fa26-01", lab, sec, None)
    assert "announced in class" in text


# ── gh teacher plumbing ──────────────────────────────────────────────────────


def test_an_existing_classroom_is_not_an_error(monkeypatch):
    monkeypatch.setattr(
        c50, "_run",
        lambda cmd, dry: (1, "short-name cecs-326-fa26-01 already exists in the repo"))
    assert c50.ensure_classroom("O", "cecs-326-fa26-01", "n", "fa26", False) == "exists"


def test_a_real_classroom_failure_still_raises(monkeypatch):
    monkeypatch.setattr(c50, "_run", lambda cmd, dry: (1, "missing scopes"))
    with pytest.raises(c50.C50Error, match="missing scopes"):
        c50.ensure_classroom("O", "cecs-326-fa26-01", "n", "fa26", False)


def test_register_assignment_passes_the_resolved_facts_through(vault, monkeypatch):
    seen = {}

    def fake(cmd, dry):
        seen["cmd"] = cmd
        return 0, ""

    monkeypatch.setattr(c50, "_run", fake)
    lab = c50.find_lab(vault, "CECS 326", 1)
    c50.register_assignment(
        "Giacalone-CECS", "cecs-326-fa26-01", lab,
        "2026-09-24T23:59:00-07:00", None, "tag", False)
    cmd = seen["cmd"]
    assert cmd[:6] == ["gh", "teacher", "assignment", "add", "Giacalone-CECS",
                       "cecs-326-fa26-01"]
    assert "lab-01-threads" in cmd
    assert "agiacalone/cecs-326-reading-processes_and_threads" in cmd
    assert cmd[cmd.index("--name") + 1] == "Lab 1 - Threads"
    assert cmd[cmd.index("--submission-mode") + 1] == "tag"


def test_post_dry_run_touches_nothing(vault, monkeypatch, capsys):
    monkeypatch.setattr(c50, "_run", lambda cmd, dry: (0, ""))
    note = vault / "classes" / "326" / "326-01-fa26.md"
    before = note.read_text()
    rc = c50.main([
        "post", "--term", "fa26", "--course", "CECS 326", "--lab", "1",
        "--due", "2026-09-24T23:59:00-07:00",
        "--vault-root", str(vault), "--dry-run",
    ])
    assert rc == 0
    assert note.read_text() == before
    assert not (vault / "classes" / "326" / "labs" / "threads" / "posted").exists()
    # both 326 sections were addressed
    out = capsys.readouterr().out
    assert "cecs-326-fa26-01" in out and "cecs-326-fa26-03" in out


def test_post_writes_one_announcement_per_section(vault, monkeypatch):
    monkeypatch.setattr(c50, "_run", lambda cmd, dry: (0, ""))
    rc = c50.main([
        "post", "--term", "fa26", "--course", "CECS 326", "--lab", "1",
        "--due", "2026-09-24T23:59:00-07:00", "--vault-root", str(vault),
    ])
    assert rc == 0
    posted = vault / "classes" / "326" / "labs" / "threads" / "posted"
    names = sorted(p.name for p in posted.iterdir())
    assert names == ["fa26-01-ANNOUNCE.md", "fa26-03-ANNOUNCE.md"]
    assert "cecs-326-fa26-03" in (posted / "fa26-03-ANNOUNCE.md").read_text()


def test_post_reports_a_vault_gap_as_an_error_not_a_traceback(vault, capsys):
    rc = c50.main([
        "post", "--term", "fa26", "--course", "CECS 326", "--lab", "9",
        "--vault-root", str(vault),
    ])
    assert rc == 2
    assert "no lab-index note" in capsys.readouterr().err


# ── frontmatter fidelity (regression: 2026-09-10 live-vault damage) ──────────

REAL_NOTE = """\
---
type: class-note
section: "01"
schedule:
  final-exam-window: "17:00-19:00"
github-classroom:
  id: null
  url: null
tags: [class-note, teaching, cecs-326, term-fa26]
created: 2026-07-08T11:31:22-07:00
updated: 2026-08-24T17:05:00-07:00
---

# CECS 326 §01 — Fall 2026

Body with `---` inside it, and a --- horizontal rule.
"""


def test_write_back_changes_only_the_lines_it_owns(tmp_path):
    """A YAML round-trip reformatted tags, quotes, and the created: timestamp.

    On 2026-09-10 that silently rewrote `created: 2026-07-08T11:31:22-07:00`
    to `2026-07-08 11:31:22-07:00` on three live class notes — dropping the
    `T` that Dataview parses dates with.
    """
    note = tmp_path / "326-01-fa26.md"
    note.write_text(REAL_NOTE)
    assert c50.write_back(note, "Giacalone-CECS", "cecs-326-fa26-01", dry_run=False)

    before = REAL_NOTE.splitlines()
    after = note.read_text().splitlines()
    changed = [l for l in after if l not in before]
    # only the two binding lines and the updated: stamp may differ
    assert all(
        l.startswith(("  id:", "  url:", "updated:")) for l in changed
    ), changed

    text = note.read_text()
    assert 'section: "01"' in text
    assert 'final-exam-window: "17:00-19:00"' in text
    assert "tags: [class-note, teaching, cecs-326, term-fa26]" in text
    assert "created: 2026-07-08T11:31:22-07:00" in text
    assert "Body with `---` inside it, and a --- horizontal rule." in text


def test_write_back_inserts_the_block_when_the_note_lacks_one(tmp_path):
    note = tmp_path / "n.md"
    note.write_text(REAL_NOTE.replace(
        "github-classroom:\n  id: null\n  url: null\n", ""))
    assert c50.write_back(note, "Giacalone-CECS", "cecs-326-fa26-01", dry_run=False)
    text = note.read_text()
    assert "github-classroom:\n  id: cecs-326-fa26-01\n" in text
    assert "tags: [class-note" in text
    assert "created: 2026-07-08T11:31:22-07:00" in text


def test_write_back_replaces_a_stale_binding_without_duplicating_it(tmp_path):
    note = tmp_path / "n.md"
    note.write_text(REAL_NOTE.replace("id: null", "id: cecs-326-sp26-01"))
    assert c50.write_back(note, "Giacalone-CECS", "cecs-326-fa26-01", dry_run=False)
    text = note.read_text()
    assert text.count("github-classroom:") == 1
    assert "cecs-326-sp26-01" not in text

import json
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


# ── roster-import ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expected", [
    ("octocat", "octocat"),
    ("  octocat  ", "octocat"),
    ("@octocat", "octocat"),
    ("https://github.com/octocat", "octocat"),
    ("http://www.github.com/octocat/", "octocat"),
    ("github.com/octocat", None),          # no scheme: too ambiguous to trust
    ("octo-cat", "octo-cat"),
    ("a" * 39, "a" * 39),
])
def test_normalize_recovers_what_students_actually_submit(raw, expected):
    assert c50.normalize_submitted_username(raw) == expected


@pytest.mark.parametrize("raw", [
    "", "   ", "octocat@student.csulb.edu", "032571160",
    "my name is octocat", "-octocat", "octocat-", "a" * 40, "octo--cat",
])
def test_normalize_refuses_rather_than_guesses(raw):
    """An email's local part is not a username. Refusing beats inviting a stranger."""
    assert c50.normalize_submitted_username(raw) is None


def test_parse_submissions_finds_the_columns_in_a_canvas_style_export(tmp_path):
    f = tmp_path / "sub.csv"
    f.write_text(
        "name,id,section,answer\n"
        '"Doe, Jane",032571160,CECS 326 Sec01,janedoe\n'
        '"Roe, Rick",027369145,CECS 326 Sec01,@rickroe\n'
    )
    pairs = c50.parse_submissions(f)
    assert pairs == [("032571160", "janedoe"), ("027369145", "@rickroe")]


def test_parse_submissions_falls_back_to_names_when_there_is_no_id(tmp_path):
    f = tmp_path / "sub.csv"
    f.write_text("student,github\nJane Doe,janedoe\nRick Roe,rickroe\n")
    assert c50.parse_submissions(f) == [("Jane Doe", "janedoe"), ("Rick Roe", "rickroe")]


def test_parse_submissions_says_so_when_no_column_holds_usernames(tmp_path):
    f = tmp_path / "sub.csv"
    f.write_text("name,score\nJane Doe,10\nRick Roe,9\n")
    with pytest.raises(c50.C50Error, match="no column looks like GitHub usernames"):
        c50.parse_submissions(f)


ROSTER_CSV = (
    "student_id,lms_name,display_name,canonical_name,section,enrollment_status\n"
    '032571160,"Doe,Jane",Jane Doe,jane doe,01,enrolled\n'
    '027369145,"Roe,Rick",Rick Roe,rick roe,01,enrolled\n'
    '099999999,"Gone,Gus",Gus Gone,gus gone,01,withdrawn\n'
)


def test_match_student_by_id_and_by_reordered_name():
    import csv, io
    roster = [r for r in csv.DictReader(io.StringIO(ROSTER_CSV))
              if r["enrollment_status"] != "withdrawn"]
    used = set()
    assert c50.match_student("032571160", roster, used)["display_name"] == "Jane Doe"
    # Canvas writes "Last, First"; the roster stores "First Last"
    assert c50.match_student("Roe, Rick", roster, used)["display_name"] == "Rick Roe"
    assert c50.match_student("Nobody At All", roster, used) is None


def test_match_student_does_not_reuse_a_row():
    import csv, io
    roster = list(csv.DictReader(io.StringIO(ROSTER_CSV)))[:2]
    used = {"032571160"}
    assert c50.match_student("032571160", roster, used) is None


def _vault_with_roster(vault: Path) -> Path:
    arch = vault / "classes" / "326" / "archives" / "fa26-01"
    arch.mkdir(parents=True, exist_ok=True)
    (arch / "roster.csv").write_text(ROSTER_CSV)
    return vault


def test_roster_import_dry_run_reports_and_writes_nothing(vault, tmp_path, monkeypatch, capsys):
    _vault_with_roster(vault)
    subs = tmp_path / "s.csv"
    subs.write_text("id,answer\n032571160,janedoe\n027369145,not an account\n")
    monkeypatch.setattr(c50, "verify_github_user", lambda u: u)
    rc = c50.main([
        "roster-import", "--term", "fa26", "--course", "CECS 326", "--section", "01",
        "--usernames", str(subs), "--vault-root", str(vault), "--dry-run",
    ])
    out = capsys.readouterr().out
    assert rc == 1                       # one submission needs a human
    assert "resolved 1/2" in out
    assert "is not a GitHub username" in out
    assert not (tmp_path / "cecs-326-fa26-01-roster.csv").exists()


def test_roster_import_flags_a_username_that_does_not_exist(vault, tmp_path, monkeypatch, capsys):
    _vault_with_roster(vault)
    subs = tmp_path / "s.csv"
    subs.write_text("id,answer\n032571160,typodname\n")
    monkeypatch.setattr(c50, "verify_github_user", lambda u: None)
    rc = c50.main([
        "roster-import", "--term", "fa26", "--course", "CECS 326", "--section", "01",
        "--usernames", str(subs), "--vault-root", str(vault), "--dry-run",
    ])
    assert rc == 1
    assert "does not exist" in capsys.readouterr().out


def test_roster_import_writes_the_c50_shape_and_imports(vault, tmp_path, monkeypatch, capsys):
    _vault_with_roster(vault)
    subs = tmp_path / "s.csv"
    subs.write_text("id,answer\n032571160,JaneDoe\n027369145,https://github.com/rickroe\n")
    monkeypatch.setattr(c50, "verify_github_user", lambda u: u)
    calls = []
    monkeypatch.setattr(c50, "_run", lambda cmd, dry: (calls.append(cmd), (0, "imported"))[1])
    out_csv = tmp_path / "roster.csv"
    rc = c50.main([
        "roster-import", "--term", "fa26", "--course", "CECS 326", "--section", "01",
        "--usernames", str(subs), "--vault-root", str(vault), "--out", str(out_csv),
    ])
    assert rc == 0
    text = out_csv.read_text()
    assert text.splitlines()[0] == "username,first_name,last_name,email,section"
    assert "JaneDoe,Jane,Doe,,01" in text
    assert "rickroe,Rick,Roe,,01" in text
    assert calls[-1][:5] == ["gh", "teacher", "roster", "import", "Giacalone-CECS"]
    assert "expires in 7 days" in capsys.readouterr().out


# ── enrolment codes ──────────────────────────────────────────────────────────


def test_codes_are_minted_once_and_reused(vault, capsys):
    rc = c50.main(["codes", "--term", "fa26", "--vault-root", str(vault)])
    assert rc == 0
    store = vault / "classes" / "semesters" / "fa26.enroll-codes.json"
    first = json.loads(store.read_text())
    assert len(first) == 3                      # one per section in the spec
    c50.main(["codes", "--term", "fa26", "--vault-root", str(vault)])
    assert json.loads(store.read_text()) == first, "a re-run must not re-mint"


def test_codes_omit_characters_students_misread(vault):
    c50.main(["codes", "--term", "fa26", "--vault-root", str(vault)])
    store = vault / "classes" / "semesters" / "fa26.enroll-codes.json"
    for code in json.loads(store.read_text()):
        suffix = code.rsplit("-", 1)[-1]
        assert not (set(suffix) & set("ILO01")), f"{code} contains a lookalike"


def test_codes_map_one_to_one_onto_the_terms_classrooms(vault):
    c50.main(["codes", "--term", "fa26", "--vault-root", str(vault)])
    store = vault / "classes" / "semesters" / "fa26.enroll-codes.json"
    codes = json.loads(store.read_text())
    assert sorted(codes.values()) == [
        "cecs-326-fa26-01", "cecs-326-fa26-03", "cecs-378-fa26-01"]
    assert len(set(codes.values())) == len(codes), "two codes share a classroom"


def test_rotate_replaces_a_code_without_orphaning_its_classroom(vault):
    c50.main(["codes", "--term", "fa26", "--vault-root", str(vault)])
    store = vault / "classes" / "semesters" / "fa26.enroll-codes.json"
    before = json.loads(store.read_text())
    c50.main(["codes", "--term", "fa26", "--course", "CECS 378", "--section", "01",
              "--vault-root", str(vault), "--rotate"])
    after = json.loads(store.read_text())
    assert sorted(after.values()) == sorted(before.values()), "a classroom lost its code"
    assert set(after) != set(before), "rotate did not change anything"
    # only the rotated section's code changed
    unchanged = {k: v for k, v in before.items() if v != "cecs-378-fa26-01"}
    assert unchanged.items() <= after.items()


def test_codes_dry_run_writes_nothing(vault):
    store = vault / "classes" / "semesters" / "fa26.enroll-codes.json"
    assert c50.main(["codes", "--term", "fa26", "--vault-root", str(vault),
                     "--dry-run"]) == 0
    assert not store.exists()


# ── regeneration safety (regression: 2026-09-10 clobbered OMEGA note) ────────


def test_announce_note_from_the_index_survives_regeneration(vault):
    """A due-date change regenerated an announcement and silently dropped a
    hand-added paragraph about which bosses were optional. The note now lives
    in the lab-index frontmatter, so regeneration reproduces it."""
    index = vault / "classes" / "326" / "labs" / "threads" / "index.md"
    index.write_text(index.read_text().replace(
        "lab-slug: threads",
        'lab-slug: threads\nannounce-note: "Only three of the four are required."'))
    lab = c50.find_lab(vault, "CECS 326", 1)
    assert lab.announce_note == "Only three of the four are required."
    text = c50.announcement("Giacalone-CECS", "cecs-326-fa26-01", lab,
                            {"course": "CECS 326", "section": "01"},
                            "2026-09-25T23:59:00-07:00")
    assert "Only three of the four are required." in text
    assert "Bring questions" in text          # the note is inserted, not substituted


def test_announcement_without_a_note_has_no_stray_blank_run(vault):
    lab = c50.find_lab(vault, "CECS 326", 1)
    assert lab.announce_note is None
    text = c50.announcement("Giacalone-CECS", "cecs-326-fa26-01", lab,
                            {"course": "CECS 326", "section": "01"}, None)
    assert "\n\n\n" not in text


def test_friday_due_date_renders_as_friday(vault):
    lab = c50.find_lab(vault, "CECS 326", 1)
    text = c50.announcement("Giacalone-CECS", "cecs-326-fa26-01", lab,
                            {"course": "CECS 326", "section": "01"},
                            "2026-09-25T23:59:00-07:00")
    assert "Friday, September 25 at 11:59 PM" in text

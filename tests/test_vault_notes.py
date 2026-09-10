import pytest
from lectern.vault_notes import course_dir, split_frontmatter, set_frontmatter_fields


def test_course_dir():
    assert course_dir("CECS 378") == "378-478"
    assert course_dir("CECS 478") == "378-478"
    assert course_dir("CECS 326") == "326"
    assert course_dir("CECS 327") == "327"


def test_split_frontmatter_roundtrip():
    text = "---\na: 1\nb: two\n---\n\n# Body\ntext\n"
    fm, body = split_frontmatter(text)
    assert fm == {"a": 1, "b": "two"}
    assert body.startswith("\n# Body")


def test_split_frontmatter_requires_frontmatter():
    with pytest.raises(ValueError):
        split_frontmatter("no frontmatter here")


def test_set_frontmatter_fields_flat_and_nested():
    text = "---\nstatus: in-progress\nheadcount:\n  enrolled: 0\n  completed: 0\nschedule:\n  room: null\n---\nBODY\n"
    out = set_frontmatter_fields(text, {
        "status": "finalized",
        "headcount.enrolled": 45,
        "schedule.room": "HC-120",
    })
    fm, body = split_frontmatter(out)
    assert fm["status"] == "finalized"
    assert fm["headcount"]["enrolled"] == 45
    assert fm["headcount"]["completed"] == 0   # untouched
    assert fm["schedule"]["room"] == "HC-120"
    assert body.strip() == "BODY"


def test_set_frontmatter_preserves_key_order():
    text = "---\nz: 1\na: 2\n---\nB\n"
    out = set_frontmatter_fields(text, {"a": 9})
    # z stays before a
    assert out.index("z:") < out.index("a:")


# ── formatting fidelity (regression: 2026-09-10 live class-note damage) ──────

REAL_NOTE = """---
type: class-note
section: "01"
schedule:
  meets: TuTh 5:30–6:45 PM
  final-exam-window: "17:00-19:00"
  final-exam-room: null
headcount:
  enrolled: 60
  withdrew: 0
github-classroom:
  id: null
tags: [class-note, teaching, cecs-326, term-fa26]
created: 2026-07-08T11:31:22-07:00
updated: 2026-08-24T17:05:00-07:00
---

# Body with a --- rule in it
"""


def test_only_the_requested_lines_change():
    """A YAML round-trip rewrote tags to block style, requoted scalars, and
    turned `created: 2026-07-08T11:31:22-07:00` into a space-separated
    timestamp, dropping the T Dataview parses. On three live notes."""
    out = set_frontmatter_fields(REAL_NOTE, {
        "headcount.enrolled": 61,
        "github-classroom.id": "cecs-326-fa26-01",
        "updated": "2026-09-10T18:00:00-07:00",
    })
    before = REAL_NOTE.splitlines()
    changed = [l for l in out.splitlines() if l not in before]
    assert len(changed) == 3, changed

    for kept in ['section: "01"',
                 'final-exam-window: "17:00-19:00"',
                 "tags: [class-note, teaching, cecs-326, term-fa26]",
                 "created: 2026-07-08T11:31:22-07:00",
                 "meets: TuTh 5:30–6:45 PM",
                 "final-exam-room: null"]:
        assert kept in out, kept
    assert "# Body with a --- rule in it" in out


def test_iso_timestamps_stay_bare_and_keep_their_T():
    out = set_frontmatter_fields(REAL_NOTE, {"updated": "2026-09-10T18:00:00-07:00"})
    assert "updated: 2026-09-10T18:00:00-07:00" in out
    assert "2026-09-10 18:00:00" not in out


def test_lists_render_flow_style_not_block():
    out = set_frontmatter_fields(REAL_NOTE, {"courses": ["CECS 326", "CECS 478"]})
    assert "courses: [CECS 326, CECS 478]" in out
    fm, _ = split_frontmatter(out)
    assert fm["courses"] == ["CECS 326", "CECS 478"]


def test_ambiguous_scalars_are_quoted():
    out = set_frontmatter_fields(REAL_NOTE, {
        "a": "true", "b": "null", "c": "123", "d": "key: value", "e": ""})
    fm, _ = split_frontmatter(out)
    assert fm["a"] == "true" and fm["b"] == "null" and fm["c"] == "123"
    assert fm["d"] == "key: value" and fm["e"] == ""


def test_a_missing_nested_key_is_inserted_under_its_parent():
    out = set_frontmatter_fields(REAL_NOTE, {"headcount.completed": 12})
    fm, _ = split_frontmatter(out)
    assert fm["headcount"]["completed"] == 12
    assert fm["headcount"]["enrolled"] == 60
    assert "tags: [class-note" in out


def test_a_missing_parent_block_is_created():
    out = set_frontmatter_fields(REAL_NOTE, {"syllabus.serial": "487BD388"})
    fm, _ = split_frontmatter(out)
    assert fm["syllabus"]["serial"] == "487BD388"

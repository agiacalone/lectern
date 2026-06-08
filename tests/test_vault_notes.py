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

import textwrap
from datetime import date
from pathlib import Path

import pytest
import yaml

from lectern import admin_form as af

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
    no-instruction:
      - { date: 2026-09-07, label: "Labor Day (campus closed)" }
    sections:
      - course: CECS 378
        title: Introduction to Computer Security Principles
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
""")

PROFILE_YAML = textwrap.dedent("""\
    form: demo
    title: Demo Form
    hours-per-day: 8
    routing:
      - { role: Chair, email: chair@example.edu, to: true }
      - { role: CC, email: cc@example.edu }
    leave-types:
      sick:
        label: Sick Leave
      personal-holiday:
        label: Personal Holiday
        omit: [justification]
        guidance: No reason required.
        defaults:
          coverage: Async work posted to Canvas.
          reason: Personal Holiday or Other Authorized Leave
    fields:
      - { label: Signer Name, key: signer-name, section: Screen 1, source: instructor.name }
      - { label: Employee Name, key: employee-name, section: Screen 2, source: instructor.name }
      - { label: Employee ID, key: employee-id, section: Screen 2, source: instructor.employee-id }
      - label: Reason
        key: reason
        section: Screen 2
        source: prompt
        choices: [Illness/Sick Leave, Personal Holiday or Other Authorized Leave, Other]
      - { label: Numbers, key: numbers, section: Screen 2, source: classes.numbers-titles, block: true }
      - { label: Type of Absence, key: leave-type, source: leave.label }
      - { label: Dates, key: absence-dates, source: absence.dates }
      - { label: Hours, key: hours, source: absence.hours }
      - { label: Contact Hours, key: contact-hours, source: absence.contact-hours }
      - { label: Classes Affected, key: classes-affected, source: classes.lines, block: true }
      - { label: Coverage, key: coverage, source: prompt, block: true }
      - { label: Justification, key: justification, source: prompt, block: true }
      - { label: Chair Email, key: chair-email, source: "literal:chair@example.edu" }
    email:
      subject: "Absence — {{leave-type}}, {{absence.dates}}"
      body: |
        Classes affected:

        {{classes.lines}}

        Coverage: {{coverage}}
""")

IDENTITY_YAML = "name: Anthony Giacalone\nemployee-id: '012345678'\n"


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    (root / "classes" / "semesters").mkdir(parents=True)
    (root / "classes" / "semesters" / "fa26.spec.yaml").write_text(SPEC_YAML)
    forms = root / "classes" / "admin-forms"
    forms.mkdir(parents=True)
    (forms / "demo.form.yaml").write_text(PROFILE_YAML)
    (forms / "identity.yaml").write_text(IDENTITY_YAML)
    return root


def render(vault, argv_extra=()):
    argv = ["render", "--form", "demo", "--term", "fa26",
            "--vault-root", str(vault), "--today", "2026-09-05",
            *argv_extra]
    return argv


def ctx_for(vault, **kw):
    import argparse
    args = argparse.Namespace(
        form="demo", dates=kw.get("dates", "2026-09-10"),
        type=kw.get("type"), term="fa26", spec=None,
        vault_root=str(vault), hours=kw.get("hours"),
        set=kw.get("set"), today="2026-09-05")
    return af.build_context(args)


# ── date parsing ────────────────────────────────────────────────────────────

def test_parse_dates_single():
    assert af.parse_dates("2026-09-10") == [date(2026, 9, 10)]


def test_parse_dates_range_is_inclusive():
    assert af.parse_dates("2026-09-08..2026-09-10") == [
        date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10)]


def test_parse_dates_comma_list_dedupes_and_sorts():
    assert af.parse_dates("2026-09-10, 2026-09-08, 2026-09-10") == [
        date(2026, 9, 8), date(2026, 9, 10)]


def test_parse_dates_rejects_backwards_range():
    with pytest.raises(af.AdminFormError):
        af.parse_dates("2026-09-10..2026-09-08")


def test_humanize_span_single_and_contiguous():
    assert af.humanize_span([date(2026, 9, 10)]) == "Thursday, September 10, 2026"
    span = af.humanize_span([date(2026, 9, 8), date(2026, 9, 9)])
    assert span == ("Tuesday, September 8, 2026 through "
                    "Wednesday, September 9, 2026")


def test_humanize_span_non_contiguous_lists_each_day():
    span = af.humanize_span([date(2026, 9, 8), date(2026, 9, 10)])
    assert " through " not in span and span.count(";") == 1


# ── resolution ──────────────────────────────────────────────────────────────

def test_fields_resolve_from_identity_and_calendar(vault):
    ctx = ctx_for(vault, type="sick")
    fields = {f["key"]: f["value"] for f in af.resolve_fields(ctx)}
    assert fields["employee-name"] == "Anthony Giacalone"
    assert fields["employee-id"] == "012345678"
    assert fields["leave-type"] == "Sick Leave"
    assert fields["absence-dates"] == "Thursday, September 10, 2026"
    assert fields["hours"] == "8"
    assert fields["contact-hours"] == "2.5"      # two 1.25h meetings
    assert "CECS 378 §01" in fields["classes-affected"]
    assert "class #1131" in fields["classes-affected"]
    assert fields["chair-email"] == "chair@example.edu"


def test_prompt_fields_are_marked_as_needing_input(vault):
    ctx = ctx_for(vault, type="sick")
    pending = [f["key"] for f in af.resolve_fields(ctx) if f["needs_input"]]
    assert pending == ["reason", "coverage", "justification"]


def test_set_overrides_a_prompt_field(vault):
    ctx = ctx_for(vault, type="sick", set=["justification=Flu."])
    fields = {f["key"]: f for f in af.resolve_fields(ctx)}
    assert fields["justification"]["value"] == "Flu."
    assert not fields["justification"]["needs_input"]


def test_set_rejects_a_value_without_an_equals(vault):
    with pytest.raises(af.AdminFormError):
        ctx_for(vault, type="sick", set=["justification"])


def test_leave_type_omit_drops_the_field_entirely(vault):
    """A contractual personal holiday is not asked to justify itself."""
    ctx = ctx_for(vault, type="personal-holiday")
    keys = [f["key"] for f in af.resolve_fields(ctx)]
    assert "justification" not in keys
    assert "coverage" in keys


def test_leave_type_defaults_prefill_a_prompt_field(vault):
    ctx = ctx_for(vault, type="personal-holiday")
    fields = {f["key"]: f for f in af.resolve_fields(ctx)}
    assert fields["coverage"]["value"] == "Async work posted to Canvas."
    assert not fields["coverage"]["needs_input"]


def test_set_still_beats_a_leave_type_default(vault):
    ctx = ctx_for(vault, type="personal-holiday", set=["coverage=Colleague covers."])
    fields = {f["key"]: f["value"] for f in af.resolve_fields(ctx)}
    assert fields["coverage"] == "Colleague covers."


def test_explicit_set_can_resurrect_an_omitted_field(vault):
    ctx = ctx_for(vault, type="personal-holiday",
                  set=["justification=Required by DocuSign."])
    fields = {f["key"]: f["value"] for f in af.resolve_fields(ctx)}
    assert fields["justification"] == "Required by DocuSign."


def test_unknown_leave_type_is_rejected(vault):
    with pytest.raises(af.AdminFormError):
        ctx_for(vault, type="sabbatical")


def test_hours_default_scales_with_the_day_count(vault):
    ctx = ctx_for(vault, type="sick", dates="2026-09-08..2026-09-10")
    fields = {f["key"]: f["value"] for f in af.resolve_fields(ctx)}
    assert fields["hours"] == "24"


def test_explicit_hours_override(vault):
    ctx = ctx_for(vault, type="sick", hours=4.0)
    fields = {f["key"]: f["value"] for f in af.resolve_fields(ctx)}
    assert fields["hours"] == "4"


def test_a_closure_day_contributes_no_meetings(vault):
    ctx = ctx_for(vault, type="sick", dates="2026-09-07")
    fields = {f["key"]: f["value"] for f in af.resolve_fields(ctx)}
    assert fields["classes-affected"].startswith("None —")
    assert "Labor Day" in ctx.skipped_days()


def test_only_the_requested_dates_are_reported(vault):
    """A Tue..Thu span must not silently bill the Wednesday it never met."""
    ctx = ctx_for(vault, type="sick", dates="2026-09-08,2026-09-10")
    assert {d.date for d in ctx.days} == {date(2026, 9, 8), date(2026, 9, 10)}
    assert len(ctx.meetings) == 4


def test_unknown_source_is_an_error(vault):
    ctx = ctx_for(vault, type="sick")
    with pytest.raises(af.AdminFormError):
        af.resolve("absence.moon-phase", ctx)


# ── rendering ───────────────────────────────────────────────────────────────

def test_form_renders_every_field_and_flags_the_pending_ones(vault):
    ctx = ctx_for(vault, type="sick")
    out = af.render_form(ctx, af.resolve_fields(ctx))
    assert "### Employee Name" in out
    assert "Fill these before submitting" in out
    assert "Coverage" in out
    assert "chair@example.edu" in out
    assert "Supporting detail" in out


def test_form_shows_the_leave_type_guidance(vault):
    ctx = ctx_for(vault, type="personal-holiday")
    out = af.render_form(ctx, af.resolve_fields(ctx))
    assert "No reason required." in out


def test_email_expands_field_and_source_tokens(vault):
    ctx = ctx_for(vault, type="personal-holiday")
    out = af.render_email(ctx, af.resolve_fields(ctx))
    assert "**To:** chair@example.edu" in out
    assert "**Cc:** cc@example.edu" in out
    assert "Absence — Personal Holiday, Thursday, September 10, 2026" in out
    assert "Async work posted to Canvas." in out
    assert "CECS 378 §01" in out
    assert "{{" not in out


def test_record_captures_the_meetings_for_later_counting(vault):
    ctx = ctx_for(vault, type="personal-holiday")
    record = yaml.safe_load(af.render_record(ctx, af.resolve_fields(ctx)))
    assert record["leave-type"] == "Personal Holiday"
    assert record["dates"] == ["2026-09-10"]
    assert record["day-count"] == 1
    assert record["submitted"] is None
    assert len(record["affected-meetings"]) == 2
    assert record["affected-meetings"][0]["class-number"] == 4785


# ── CLI ─────────────────────────────────────────────────────────────────────

def test_render_writes_the_three_products(vault, tmp_path, capsys):
    out = tmp_path / "out"
    rc = af.main(render(vault, ["--type", "sick", "--dates", "2026-09-10",
                                "--out", str(out)]))
    assert rc == 0
    assert (out / "FORM.md").exists()
    assert (out / "EMAIL.md").exists()
    assert (out / "record.yaml").exists()


def test_render_default_outdir_lands_in_the_vault(vault, capsys):
    rc = af.main(render(vault, ["--type", "sick", "--dates", "2026-09-10"]))
    assert rc == 0
    expected = (vault / "classes" / "admin-forms" / "records"
                / "2026-09-10-demo-sick" / "FORM.md")
    assert expected.exists()


def test_stdout_only_writes_nothing(vault, capsys):
    rc = af.main(render(vault, ["--type", "sick", "--dates", "2026-09-10",
                                "--stdout-only"]))
    assert rc == 0
    assert not (vault / "classes" / "admin-forms" / "records").exists()
    assert "Demo Form" in capsys.readouterr().out


def test_unknown_form_exits_nonzero(vault, capsys):
    rc = af.main(["render", "--form", "nope", "--dates", "2026-09-10",
                  "--term", "fa26", "--vault-root", str(vault)])
    assert rc == 2
    assert "no form profile" in capsys.readouterr().err


def test_list_shows_builtin_and_vault_profiles(vault, capsys):
    assert af.main(["list", "--vault-root", str(vault)]) == 0
    out = capsys.readouterr().out
    assert "demo" in out and "notice-of-absence" in out


def test_init_is_idempotent(tmp_path, capsys):
    root = tmp_path / "v"
    assert af.main(["init", "--vault-root", str(root)]) == 0
    identity = root / "classes" / "admin-forms" / "identity.yaml"
    identity.write_text("name: Edited\n")
    assert af.main(["init", "--vault-root", str(root)]) == 0
    assert identity.read_text() == "name: Edited\n"       # never clobbered


def test_vault_profile_shadows_the_builtin(vault, tmp_path):
    shadow = vault / "classes" / "admin-forms" / "notice-of-absence.form.yaml"
    shadow.write_text(PROFILE_YAML.replace("title: Demo Form",
                                           "title: Local Override"))
    path = af.find_profile("notice-of-absence", vault)
    assert path == shadow
    assert af.load_profile(path)["title"] == "Local Override"


def test_profile_missing_a_required_key_is_rejected(tmp_path):
    bad = tmp_path / "bad.form.yaml"
    bad.write_text("form: x\ntitle: X\n")
    with pytest.raises(af.AdminFormError):
        af.load_profile(bad)


# ── syllabus topic lookup ───────────────────────────────────────────────────

SYLLABUS = textwrap.dedent("""\
    ## Tentative Schedule

    | Week of | Subject |
    |------|---------|
    | **Aug 24** | Intro to Computer Security |
    | **Sep  7** | Symmetric and Asymmetric Encryption |
    | **Sep 28** | 🅰 **Exam 1** · Malicious Software |
    | **Nov 23** | User Authentication — ⚠ **Thanksgiving: no Thursday class** |

    > [!NOTE]
    > The schedule is tentative.
""")


def test_syllabus_topics_parses_the_week_of_table(tmp_path):
    path = tmp_path / "syl.md"
    path.write_text(SYLLABUS)
    topics = af.syllabus_topics(path, 2026)
    assert topics[date(2026, 8, 24)] == "Intro to Computer Security"
    assert topics[date(2026, 9, 7)] == "Symmetric and Asymmetric Encryption"


def test_syllabus_topic_strips_emoji_and_bold(tmp_path):
    path = tmp_path / "syl.md"
    path.write_text(SYLLABUS)
    assert af.syllabus_topics(path, 2026)[date(2026, 9, 28)] == \
        "Exam 1 · Malicious Software"


def test_syllabus_topics_stops_at_the_end_of_the_table(tmp_path):
    path = tmp_path / "syl.md"
    path.write_text(SYLLABUS)
    assert len(af.syllabus_topics(path, 2026)) == 4


def test_topic_is_attached_to_the_meeting_for_that_week(vault):
    syl = vault / "classes" / "syllabi" / "fa26"
    syl.mkdir(parents=True)
    (syl / "cecs-378-01-fa26-4785-github.md").write_text(SYLLABUS)
    ctx = ctx_for(vault, type="sick")            # Thu 2026-09-10, week of Sep 7
    topics = {m.label: m.topic for m in ctx.meetings}
    assert topics["CECS 378 §01"] == "Symmetric and Asymmetric Encryption"
    assert topics["CECS 326 §01"] is None        # no syllabus for that section


def test_missing_syllabus_leaves_topics_empty_rather_than_failing(vault):
    ctx = ctx_for(vault, type="sick")
    assert all(m.topic is None for m in ctx.meetings)


def test_email_addressing_can_differ_from_docusign_routing(vault):
    """Who signs the form and who gets the heads-up are different questions."""
    profile = vault / "classes" / "admin-forms" / "demo.form.yaml"
    profile.write_text(PROFILE_YAML.replace(
        "email:\n  subject:",
        "email:\n  to: clerk@example.edu\n"
        "  cc: [chair@example.edu]\n  subject:"))
    ctx = ctx_for(vault, type="sick")
    out = af.render_email(ctx, af.resolve_fields(ctx))
    assert "**To:** clerk@example.edu" in out
    assert "**Cc:** chair@example.edu" in out


# ── the Obsidian record note ────────────────────────────────────────────────

def test_note_has_queryable_frontmatter(vault):
    ctx = ctx_for(vault, type="personal-holiday")
    note = af.render_note(ctx, af.resolve_fields(ctx))
    fm = yaml.safe_load(note.split("---")[1])
    assert fm["type"] == "absence-record"
    assert fm["leave-type"] == "Personal Holiday"
    assert fm["dates"] == ["2026-09-10"]
    assert fm["contact-hours"] == 2.5
    assert fm["sections-affected"] == ["CECS 378 §01", "CECS 326 §01"]
    assert "term-fa26" in fm["tags"]


def test_note_starts_as_a_draft_awaiting_a_human(vault):
    """Only a person knows DocuSign actually went through."""
    ctx = ctx_for(vault, type="sick")
    fm = yaml.safe_load(af.render_note(ctx, af.resolve_fields(ctx)).split("---")[1])
    assert fm["status"] == "draft"
    assert fm["submitted"] is None


def test_note_lists_what_is_still_missing(vault):
    ctx = ctx_for(vault, type="sick")
    note = af.render_note(ctx, af.resolve_fields(ctx))
    assert "Still needed before this can be submitted" in note
    assert "Coverage" in note


def test_note_omits_the_reason_section_for_a_personal_holiday(vault):
    ctx = ctx_for(vault, type="personal-holiday")
    note = af.render_note(ctx, af.resolve_fields(ctx))
    assert "## Reason given" not in note
    assert "## Coverage" in note


def test_note_carries_the_routing_and_the_meetings(vault):
    ctx = ctx_for(vault, type="sick")
    note = af.render_note(ctx, af.resolve_fields(ctx))
    assert "chair@example.edu" in note
    assert "CECS 378 §01" in note
    assert "| Date | Course | Class # | Time | Room | Topic scheduled |" in note


def test_render_writes_the_note_alongside_the_other_products(vault, tmp_path):
    out = tmp_path / "out"
    af.main(render(vault, ["--type", "sick", "--dates", "2026-09-10",
                           "--out", str(out)]))
    assert (out / "2026-09-10-demo.md").exists()


# ── section grouping (the form's own box order) ─────────────────────────────

def test_fields_render_grouped_under_their_section_headings(vault):
    ctx = ctx_for(vault, type="sick")
    out = af.render_form(ctx, af.resolve_fields(ctx))
    assert "## Screen 1" in out and "## Screen 2" in out
    # a paste-per-box block is only useful in box order
    assert out.index("## Screen 1") < out.index("## Screen 2")
    assert out.index("### Signer Name") < out.index("### Employee Name")


def test_a_section_heading_is_emitted_once_per_run_not_per_field(vault):
    ctx = ctx_for(vault, type="sick")
    out = af.render_form(ctx, af.resolve_fields(ctx))
    assert out.count("## Screen 2\n") == 1


def test_fields_without_a_section_fall_under_a_plain_heading(vault):
    ctx = ctx_for(vault, type="sick")
    out = af.render_form(ctx, af.resolve_fields(ctx))
    assert "## Fields" in out          # the demo's unsectioned tail


def test_the_note_carries_the_same_ordered_block(vault):
    ctx = ctx_for(vault, type="sick")
    note = af.render_note(ctx, af.resolve_fields(ctx))
    assert "Fields, in the order the form asks for them" in note
    assert "### Screen 1" in note
    assert note.index("### Screen 1") < note.index("### Screen 2")


def test_section_survives_a_set_override(vault):
    ctx = ctx_for(vault, type="sick", set=["employee-name=Someone Else"])
    fields = {f["key"]: f for f in af.resolve_fields(ctx)}
    assert fields["employee-name"]["section"] == "Screen 2"


# ── "Class Number and Title" + checkbox choices ─────────────────────────────

def test_numbers_titles_pairs_the_class_number_with_the_catalog_title(vault):
    ctx = ctx_for(vault, type="sick")
    lines = ctx.numbers_titles().splitlines()
    assert lines[0] == "4785 — CECS 378 §01, Introduction to Computer Security Principles"
    assert lines[1] == "1131 — CECS 326 §01"      # no title in the spec for this one


def test_numbers_titles_dedupes_across_a_multi_day_absence(vault):
    """A Tue+Thu absence hits each section twice; the form wants each once."""
    ctx = ctx_for(vault, type="sick", dates="2026-09-08,2026-09-10")
    assert len(ctx.meetings) == 4
    assert len(ctx.numbers_titles().splitlines()) == 2


def test_a_choice_field_renders_as_a_tick_list(vault):
    ctx = ctx_for(vault, type="personal-holiday")
    out = af.render_form(ctx, af.resolve_fields(ctx))
    assert "- [x] Personal Holiday or Other Authorized Leave" in out
    assert "- [ ] Illness/Sick Leave" in out


def test_a_leave_type_default_picks_the_right_checkbox(vault):
    ctx = ctx_for(vault, type="personal-holiday")
    fields = {f["key"]: f["value"] for f in af.resolve_fields(ctx)}
    assert fields["reason"] == "Personal Holiday or Other Authorized Leave"


def test_an_unticked_choice_field_shows_every_box_empty(vault):
    ctx = ctx_for(vault, type="sick")          # no default reason on this type
    out = af.render_form(ctx, af.resolve_fields(ctx))
    assert "- [ ] Personal Holiday or Other Authorized Leave" in out
    assert "- [x]" not in out


def test_a_value_outside_the_choices_is_rejected(vault):
    """A typo'd checkbox is a profile bug, not something to paste blindly."""
    ctx = ctx_for(vault, type="sick", set=["reason=Sabbatical"])
    with pytest.raises(af.AdminFormError, match="not one of its choices"):
        af.resolve_fields(ctx)



def test_a_section_split_across_the_profile_is_rejected(tmp_path):
    """Field order is box order, so a reappearing section is an authoring slip."""
    bad = tmp_path / "bad.form.yaml"
    bad.write_text(textwrap.dedent("""\
        form: bad
        title: Bad
        fields:
          - { label: A, section: One, source: "literal:a" }
          - { label: B, section: Two, source: "literal:b" }
          - { label: C, section: One, source: "literal:c" }
    """))
    with pytest.raises(af.AdminFormError, match="split apart"):
        af.load_profile(bad)

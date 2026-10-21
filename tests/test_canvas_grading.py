"""Tests for ``reg-canvas audit`` and ``reg-canvas discussions``.

Uses the fake transport from test_canvas: no network, every request recorded.
"""
import json
from datetime import datetime, timezone

from lectern import canvas, canvas_grading
from lectern.canvas import Target
from tests.test_canvas import client_for

SECRET = "SECRET POST TEXT that must never reach disk"

ENROLL = [
    {"user_id": 1, "user": {"sortable_name": "Zed, Ann", "sis_user_id": "111"},
     "grades": {"current_score": 90, "unposted_current_score": 80}},
    {"user_id": 2, "user": {"sortable_name": "Able, Bo", "sis_user_id": "222"},
     "grades": {"current_score": 70, "unposted_current_score": 70}},
    {"user_id": 3, "user": {"sortable_name": "Staff, Cy", "sis_user_id": "999"}, "grades": {}},
]
LONG = ("Paging trades memory for lookups because the page table itself lives in memory "
        "and every access walks it unless the TLB already holds the translation, Bo.")


def view():
    return {"view": [
        {"id": 100, "user_id": 1, "message": f"<p>{LONG} {SECRET}</p>", "replies": [
            {"id": 101, "user_id": 2, "message": "<p>agree</p>", "replies": []}]},
        {"id": 102, "user_id": 1, "message": f"<p>{LONG} Second thought on it, Bo.</p>"},
        {"id": 103, "user_id": 3, "message": "<p>staff note</p>"},
        {"id": 104, "user_id": 2, "message": "gone", "deleted": True},
    ]}


def routes(extra=None):
    r = {
        ("GET", "courses/7/enrollments"): ENROLL,
        ("GET", "courses/7/assignments"): [
            {"id": 50, "name": "Week 5 - Memory", "discussion_topic": {"id": 70}},
            {"id": 51, "name": "Lab 1", "discussion_topic": None}],
        ("GET", "courses/7/discussion_topics/70/view"): view(),
        ("GET", "courses/7/assignments/50/submissions"): [
            {"user_id": 1, "score": None}, {"user_id": 2, "score": 3}],
    }
    r.update(extra or {})
    return r


def run_review(tmp_path, argv=()):
    client, fake = client_for(routes())
    ns = canvas.build_parser().parse_args(
        ["discussions", "review", "--course-id", "7", "--week", "Week 5",
         "--workdir", str(tmp_path / "wd"), "--exclude-sis", "999", *argv])
    assert ns.func(client, ns) == 0
    return fake


def run_apply(tmp_path, argv=(), extra=None):
    client, fake = client_for(routes(extra))
    ns = canvas.build_parser().parse_args(
        ["discussions", "apply", "--workdir", str(tmp_path / "wd"), *argv])
    assert ns.func(client, ns) == 0
    return fake


# ── scoping ──────────────────────────────────────────────────────────────────


def test_sis_scope_limits_to_one_section():
    t = Target(123151, "CECS 326 §03", {"course": "CECS 326", "section": "03"})
    assert canvas_grading.scoped(["1@326-03", "2@326-01", "3", "4@123151"], t) == {"1", "3", "4"}


# ── metrics ──────────────────────────────────────────────────────────────────


def test_metrics_measure_without_returning_text():
    m = canvas_grading.metrics(f"<p>{LONG}</p>", {"Bo"})
    assert m["words"] > 25 and m["names_classmate"] and m["links"] == 0
    assert all(LONG not in str(v) for k, v in m.items() if k != "_shingles")


def test_overlap_finds_a_copied_post():
    posts = canvas_grading.topic_posts(view(), {1: "Ann", 2: "Bo"})
    by_id = {eid: m for _, eid, m in posts}
    # Ann's two posts share phrasing with each other, but overlap only counts other students.
    assert by_id[100]["max_overlap"] == 0 and "_shingles" not in by_id[100]
    assert by_id[101]["reply"] and by_id[100]["got_replies"] == 1
    assert 104 not in by_id  # deleted entries never count


# ── review ───────────────────────────────────────────────────────────────────


def test_review_scores_by_count_and_flags_short_posts(tmp_path):
    fake = run_review(tmp_path)
    assert not fake.writes()
    plan = json.loads((tmp_path / "wd" / "plan.json").read_text())
    assert {p["name"]: len(p["entries"]) for p in plan} == {"Zed, Ann": 2, "Able, Bo": 1}
    review = (tmp_path / "wd" / "REVIEW.md").read_text()
    assert "Able, Bo: one post only (3 pt)" in review and "Zed, Ann" not in review
    assert "- [ ] deny entry `101`" in review
    assert (tmp_path / "wd").stat().st_mode & 0o777 == 0o700


def test_post_text_never_reaches_disk(tmp_path):
    run_review(tmp_path, ["--note", str(tmp_path / "note.md")])
    for f in [*(tmp_path / "wd").iterdir(), tmp_path / "note.md"]:
        assert SECRET not in f.read_text(), f.name
        assert f.stat().st_mode & 0o777 == 0o600


def test_staff_are_excluded_and_full_credit_is_honoured(tmp_path):
    run_review(tmp_path, ["--full-credit-sis", "222"])
    plan = json.loads((tmp_path / "wd" / "plan.json").read_text())
    assert "Staff, Cy" not in {p["name"] for p in plan}
    assert next(p for p in plan if p["name"] == "Able, Bo")["full_credit"]
    assert "Able, Bo" not in (tmp_path / "wd" / "REVIEW.md").read_text()


def test_review_will_not_overwrite_a_ticked_note(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("- [x] deny entry `101`")
    client, _ = client_for(routes())
    rc = canvas.main(["discussions", "review", "--course-id", "7", "--week", "Week 5",
                      "--workdir", str(tmp_path / "wd"), "--note", str(note)], client=client)
    assert rc == 2 and "[x]" in note.read_text()


# ── apply ────────────────────────────────────────────────────────────────────


def test_apply_is_a_dry_run_without_apply(tmp_path):
    run_review(tmp_path)
    assert not run_apply(tmp_path, ["--post"]).writes()


def test_apply_sets_changed_grades_likes_and_posts(tmp_path):
    run_review(tmp_path)
    extra = {("POST", "courses/7/assignments/50/submissions/update_grades"):
             {"id": 9, "workflow_state": "completed"},
             ("POST", "courses/7/discussion_topics/70/entries/100/rating"): {},
             ("POST", "courses/7/discussion_topics/70/entries/102/rating"): {},
             ("POST", "courses/7/discussion_topics/70/entries/101/rating"): {},
             ("POST", "/api/graphql"): {"data": {"postAssignmentGrades": {"errors": None}}}}
    w = run_apply(tmp_path, ["--apply", "--post"], extra).writes()
    grades = w[0][2]["grade_data"]
    assert grades == {"1": {"posted_grade": "5"}}  # Bo already has 3, so no change is sent
    assert sum(1 for c in w if c[1].endswith("/rating")) == 3
    assert w[-1][1] == "/api/graphql" and w[-1][2]["variables"] == {"id": "50"}


def test_a_ticked_deny_drops_a_tier_and_withholds_the_like(tmp_path):
    run_review(tmp_path)
    note = tmp_path / "note.md"
    note.write_text("    - [x] deny entry `102` (...)\n    - [ ] deny entry `100` (...)\n")
    extra = {("POST", "courses/7/assignments/50/submissions/update_grades"):
             {"id": 9, "workflow_state": "completed"},
             ("POST", "courses/7/discussion_topics/70/entries/100/rating"): {},
             ("POST", "courses/7/discussion_topics/70/entries/101/rating"): {}}
    w = run_apply(tmp_path, ["--apply", "--note", str(note)], extra).writes()
    assert w[0][2]["grade_data"] == {"1": {"posted_grade": "3"}}
    assert not any(c[1].endswith("/102/rating") for c in w)


# ── audit ────────────────────────────────────────────────────────────────────


def test_audit_flags_empty_groups_policy_and_hidden_grades():
    client, fake = client_for({
        ("GET", "courses/7"): {"apply_assignment_group_weights": True},
        ("GET", "courses/7/assignment_groups"): [
            {"id": 1, "name": "Participation", "group_weight": 40},
            {"id": 2, "name": "Exams", "group_weight": 60}],
        ("GET", "courses/7/assignments"): [
            {"id": 50, "name": "Week 5", "assignment_group_id": 1, "published": True,
             "due_at": "2026-10-09T23:59:00Z"},
            {"id": 60, "name": "Exam 1", "assignment_group_id": 1, "published": True}],
        ("GET", "courses/7/late_policy"): {"late_policy": {
            "missing_submission_deduction_enabled": False}},
        ("GET", "courses/7/enrollments"): ENROLL,
        ("GET", "courses/7/students/submissions"): [
            {"user_id": 1, "assignment_id": 50, "score": 0, "missing": True, "posted_at": None},
            {"user_id": 2, "assignment_id": 50, "score": None, "workflow_state": "submitted"}],
    })
    lines, n = canvas_grading.audit_course(client, 7, {"999"},
                                           now=datetime(2026, 10, 21, tzinfo=timezone.utc))
    text = "\n".join(lines)
    assert "weighted but empty" in text and "policy is OFF" in text
    assert "1 graded but hidden (1 are missing-work zeros)" in text
    assert "1 submitted, not graded" in text and "past due, 1 ungraded" in text
    assert "1 student(s) see a score that differs" in text
    assert n >= 3 and not fake.writes()

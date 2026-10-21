"""Tests for the Canvas API client and ``reg-canvas``.

No network: a fake transport answers by (method, path) and records every
request, so the tests can assert both what was read and that dry runs write
nothing.
"""
import csv
import json
import os
import urllib.parse
from pathlib import Path

import pytest

from lectern import canvas, canvas_api, lms_grades
from lectern.canvas_api import CanvasClient, CanvasError
from tests.test_c50 import CLASS_NOTE, SPEC_YAML

TOKEN = "1234~AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
BASE = "https://canvas.test"


class FakeCanvas:
    """A transport that serves canned JSON and records requests."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method, url, headers, body):
        assert headers["Authorization"] == f"Bearer {TOKEN}"
        parts = urllib.parse.urlsplit(url)
        path = parts.path.removeprefix("/api/v1/")
        data = json.loads(body) if body else None
        self.calls.append((method, path, data))
        page = dict(urllib.parse.parse_qsl(parts.query)).get("page")
        key = (method, path) if page is None else (method, f"{path}#{page}")
        resp = self.routes.get(key)
        if resp is None:
            return 404, {}, json.dumps({"errors": [{"message": f"no route {key}"}]}).encode()
        if callable(resp):
            resp = resp(data)
        status, hdrs, payload = resp if isinstance(resp, tuple) else (200, {}, resp)
        return status, hdrs, json.dumps(payload).encode()

    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]


def client_for(routes) -> tuple[CanvasClient, FakeCanvas]:
    fake = FakeCanvas(routes)
    return CanvasClient(BASE, TOKEN, transport=fake, sleep=lambda s: None), fake


# A two-student course: one graded, one excused, one Test Student absent
# (Canvas files those under StudentViewEnrollment, which is never requested).
ASSIGNMENTS = [
    {"id": 11, "name": "Lab 1 - Threads", "points_possible": 60, "assignment_group_id": 2,
     "position": 1, "published": True, "post_manually": True},
    {"id": 10, "name": "Week 1 - Intro", "points_possible": 5, "assignment_group_id": 1,
     "position": 1, "published": True, "post_manually": False},
    {"id": 12, "name": "Hidden", "points_possible": 1, "assignment_group_id": 1,
     "position": 2, "published": True, "hide_in_gradebook": True},
]
GROUPS = [{"id": 1, "name": "Class Participation", "position": 1},
          {"id": 2, "name": "Assignments and Labs", "position": 2}]
ENROLLMENTS = [
    {"user_id": 501, "course_section_id": 9,
     "user": {"id": 501, "sortable_name": "Zed, Ann", "sis_user_id": "12345678",
              "login_id": "012345678"},
     "grades": {"current_score": 91.5, "final_score": 80, "current_grade": "A",
                "final_grade": "B"}},
    {"user_id": 502, "course_section_id": 9,
     "user": {"id": 502, "sortable_name": "Able, Bo", "sis_user_id": "023456789",
              "login_id": "023456789"},
     "grades": {"current_score": None, "final_score": 0}},
]
SUBMISSIONS = [
    {"user_id": 501, "assignment_id": 10, "score": 5, "excused": False,
     "body": "SECRET ESSAY TEXT", "url": "https://x", "attachments": [{"url": "y"}]},
    {"user_id": 501, "assignment_id": 11, "score": 55.5, "excused": False},
    {"user_id": 502, "assignment_id": 10, "score": None, "excused": True},
]


def course_routes(cid=77):
    p = f"courses/{cid}"
    return {
        ("GET", f"{p}/assignment_groups"): GROUPS,
        ("GET", f"{p}/assignments"): ASSIGNMENTS,
        ("GET", f"{p}/sections"): [{"id": 9, "name": "CECS 326 Sec01 1131"}],
        ("GET", f"{p}/enrollments"): ENROLLMENTS,
        ("GET", f"{p}/students/submissions"): SUBMISSIONS,
        ("GET", f"{p}/discussion_topics"): [{"title": "Old news"}],
    }


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / "classes" / "semesters").mkdir(parents=True)
    (root / "classes" / "semesters" / "fa26.spec.yaml").write_text(SPEC_YAML)
    (root / "classes" / "326").mkdir(parents=True)
    (root / "classes" / "326" / "326-01-fa26.md").write_text(CLASS_NOTE)
    return root


# ── token handling ───────────────────────────────────────────────────────────


def write_token(tmp_path, text=TOKEN, mode=0o600) -> Path:
    p = tmp_path / "canvas-token"
    p.write_text(text + "\n")
    p.chmod(mode)
    return p


def test_token_loads_from_an_owner_only_file(tmp_path):
    assert canvas_api.load_token(write_token(tmp_path)) == TOKEN


def test_a_group_readable_token_file_is_refused(tmp_path):
    with pytest.raises(CanvasError, match="chmod 600"):
        canvas_api.load_token(write_token(tmp_path, mode=0o644))


def test_a_malformed_token_is_refused_without_echoing_it(tmp_path):
    bad = '"' + TOKEN + '"'
    with pytest.raises(CanvasError) as e:
        canvas_api.load_token(write_token(tmp_path, bad))
    assert TOKEN not in str(e.value)


def test_a_missing_token_file_says_where_it_looked(tmp_path):
    with pytest.raises(CanvasError, match="no Canvas token"):
        canvas_api.load_token(tmp_path / "nope")


def test_base_url_reads_the_config_file(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[canvas]\nbase_url = "https://canvas.example.edu/"\n')
    monkeypatch.delenv("LECTERN_CANVAS_URL", raising=False)
    monkeypatch.setattr(canvas_api, "CONFIG", cfg)
    assert canvas_api.base_url() == "https://canvas.example.edu"


# ── client ───────────────────────────────────────────────────────────────────


def test_get_all_follows_next_links():
    nxt = {"Link": f'<{BASE}/api/v1/things?page=2>; rel="next"'}
    client, fake = client_for({
        ("GET", "things"): (200, nxt, [{"id": 1}]),
        ("GET", "things#2"): [{"id": 2}],
    })
    assert [x["id"] for x in client.get_all("things")] == [1, 2]


def test_the_token_is_never_sent_to_another_host():
    evil = {"Link": '<https://evil.test/api/v1/things?page=2>; rel="next"'}
    client, fake = client_for({("GET", "things"): (200, evil, [{"id": 1}])})
    with pytest.raises(CanvasError, match="refusing to send the token"):
        list(client.get_all("things"))
    assert len(fake.calls) == 1


def test_an_error_echoing_the_token_is_scrubbed():
    client, _ = client_for({("GET", "x"): (401, {}, {"errors": [{"message": f"bad {TOKEN}"}]})})
    with pytest.raises(CanvasError) as e:
        client.get("x")
    assert TOKEN not in str(e.value) and "[token]" in str(e.value)
    assert e.value.status == 401


def test_rate_limiting_is_retried():
    answers = iter([(403, {}, {"errors": "Rate Limit Exceeded"}), (200, {}, {"ok": 1})])
    client, _ = client_for({("GET", "x"): lambda d: next(answers)})
    assert client.get("x") == {"ok": 1}


def test_redirects_are_refused_by_the_default_opener():
    handler = canvas_api._NoRedirect()
    with pytest.raises(Exception, match="refused redirect"):
        handler.redirect_request(type("R", (), {"full_url": "u"})(), None, 302, "", {}, "https://x")


# ── gradebook export ─────────────────────────────────────────────────────────


def test_read_gradebook_keeps_only_score_fields():
    client, _ = client_for(course_routes())
    gb = canvas.read_gradebook(client, 77)
    for s in gb.scores.values():
        assert set(s) == set(canvas.SCORE_FIELDS)
    assert "SECRET ESSAY TEXT" not in repr(gb)


def test_export_matches_the_canvas_layout_and_round_trips(tmp_path):
    client, _ = client_for(course_routes())
    rows = canvas.gradebook_rows(canvas.read_gradebook(client, 77))
    headers, posting, points = rows[:3]
    assert headers[:5] == canvas.IDENTITY_COLS
    # Group order, then position; the hidden column is left out.
    assert headers[5:7] == ["Week 1 - Intro (10)", "Lab 1 - Threads (11)"]
    assert posting[5:7] == ["", "Manual Posting"]
    assert points[0] == "    Points Possible" and points[5:7] == ["5.00", "60.00"]
    assert points[headers.index("Override Score")] == ""
    assert points[headers.index("Current Score")] == "(read only)"
    # Students in sortable-name order; EX and blanks as Canvas writes them.
    assert [r[0] for r in rows[3:]] == ["Able, Bo", "Zed, Ann"]
    assert rows[3][5:7] == ["EX", ""]
    assert rows[4][5:7] == ["5.00", "55.50"]

    out = tmp_path / "export.csv"
    canvas.write_csv(rows, out)
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    norm = lms_grades.normalize_grades(lms_grades.parse_canvas_csv(out))
    zed = next(g for g in norm.grades if g.display_name == "Zed, Ann")
    assert zed.student_id == "012345678"          # re-padded to nine digits
    assert json.loads(zed.assignment_scores) == {"Lab 1 - Threads": "55.50",
                                                 "Week 1 - Intro": "5.00"}
    assert zed.current_score == "91.50" and zed.final_grade == "B"


def test_grades_export_writes_into_the_archive_by_default(vault, monkeypatch):
    note = vault / "classes" / "326" / "326-01-fa26.md"
    note.write_text(note.read_text().replace("---\n\n#", "canvas:\n  course-id: 77\n---\n\n#", 1))
    client, _ = client_for(course_routes())
    rc = canvas.main(["grades-export", "--term", "fa26", "--vault-root", str(vault),
                      "--course", "CECS 326", "--section", "01"], client=client)
    assert rc == 0
    out = list((vault / "classes" / "326" / "archives" / "fa26-01" / "canvas").glob("*.csv"))
    assert len(out) == 1 and out[0].name.endswith("_Grades-CECS_326_Sec01.csv")


# ── binding ──────────────────────────────────────────────────────────────────


COURSES = [
    {"id": 123142, "name": "CECS 326 Sec01 1131 Operating Systems", "term": {"name": "Fall 2026"}},
    {"id": 50000, "name": "CECS 326 Sec01 1131 Operating Systems", "term": {"name": "Fall 2021"}},
    {"id": 123151, "name": "CECS 326 Sec03 10674 Operating Systems", "term": {"name": "Fall 2026"}},
]


def test_a_recurring_class_number_is_settled_by_the_term():
    sec = {"course": "CECS 326", "section": "01", "class-number": 1131}
    assert canvas.match_course(COURSES, sec, "Fall 2026")["id"] == 123142


def test_no_match_is_an_error_naming_the_section():
    sec = {"course": "CECS 378", "section": "01", "class-number": 4785}
    with pytest.raises(canvas.CanvasCmdError, match="CECS 378 §01"):
        canvas.match_course(COURSES, sec, "Fall 2026")


def test_bind_records_the_course_id_in_the_class_note(vault):
    client, _ = client_for({("GET", "courses"): COURSES})
    rc = canvas.main(["courses", "--bind", "--term", "fa26", "--vault-root", str(vault),
                      "--course", "CECS 326", "--section", "01"], client=client)
    assert rc == 0
    note = (vault / "classes" / "326" / "326-01-fa26.md").read_text()
    assert "canvas:\n  course-id: 123142\n  url: https://canvas.test/courses/123142" in note


def test_an_unbound_section_points_at_bind(vault, capsys):
    client, _ = client_for({})
    rc = canvas.main(["grades-export", "--term", "fa26", "--vault-root", str(vault),
                      "--course", "CECS 326", "--section", "01"], client=client)
    assert rc == 2 and "courses --bind" in capsys.readouterr().err


# ── grades push ──────────────────────────────────────────────────────────────


def import_file(tmp_path, rows) -> Path:
    p = tmp_path / "import.csv"
    with p.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Student", "ID", "SIS User ID", "SIS Login ID", "Section",
                    "Week 1 - Intro (10)", "Lab 1 - Threads (11)", "Current Score"])
        w.writerow(["    Points Possible", "", "", "", "", "5.00", "60.00", "(read only)"])
        w.writerows(rows)
    return p


def push_routes(cid=77):
    r = course_routes(cid)
    r[("POST", f"courses/{cid}/assignments/11/submissions/update_grades")] = {
        "id": 1, "workflow_state": "queued", "url": f"{BASE}/api/v1/progress/1"}
    r[("GET", "progress/1")] = {"id": 1, "workflow_state": "completed"}
    return r


def test_push_plans_only_changed_cells(tmp_path):
    client, _ = client_for(course_routes())
    gb = canvas.read_gradebook(client, 77)
    cols, rows = canvas.parse_import_csv(import_file(tmp_path, [
        ["Zed, Ann", "501", "12345678", "", "", "5.00", "58"],   # lab changed
        ["Able, Bo", "502", "023456789", "", "", "EX", ""],      # same, blank lab
        ["Ghost, G", "999", "999999999", "", "", "5", "60"],     # not enrolled
    ]))
    changes, warnings = canvas.plan_push(gb, cols, rows, None)
    assert [(c.sis, c.assignment_id, c.old, c.new) for c in changes] == [("012345678", 11, "55.50", "58")]
    assert any("not enrolled" in w for w in warnings)


def test_push_refuses_another_courses_file(tmp_path):
    client, _ = client_for(course_routes())
    gb = canvas.read_gradebook(client, 77)
    cols = {999: "Lab 9 (999)"}
    with pytest.raises(canvas.CanvasCmdError, match="wrong section"):
        canvas.plan_push(gb, cols, [], None)


def test_push_is_a_dry_run_without_apply(tmp_path):
    client, fake = client_for(push_routes())
    f = import_file(tmp_path, [["Zed, Ann", "501", "12345678", "", "", "5", "58"]])
    rc = canvas.main(["grades-push", "--course-id", "77", "--file", str(f)], client=client)
    assert rc == 0 and fake.writes() == []


def test_push_apply_posts_one_bulk_update(tmp_path):
    client, fake = client_for(push_routes())
    f = import_file(tmp_path, [["Zed, Ann", "501", "12345678", "", "", "5", "58"]])
    rc = canvas.main(["grades-push", "--course-id", "77", "--file", str(f), "--apply"],
                     client=client)
    assert rc == 0
    assert fake.writes() == [("POST", "courses/77/assignments/11/submissions/update_grades",
                              {"grade_data": {"501": {"posted_grade": "58"}}})]


# ── content ──────────────────────────────────────────────────────────────────


def test_announce_dry_run_writes_nothing(tmp_path):
    f = tmp_path / "a.html"
    f.write_text("<p>hello</p>")
    client, fake = client_for(course_routes())
    rc = canvas.main(["announce", "--course-id", "77", "--file", str(f), "--title", "New"],
                     client=client)
    assert rc == 0 and fake.writes() == []


def test_announce_skips_a_title_that_already_exists(tmp_path, capsys):
    f = tmp_path / "a.html"
    f.write_text("<p>hello</p>")
    client, fake = client_for(course_routes())
    canvas.main(["announce", "--course-id", "77", "--file", str(f), "--title", "Old news",
                 "--apply"], client=client)
    assert fake.writes() == [] and "already exists" in capsys.readouterr().out


def test_announce_apply_posts_an_announcement(tmp_path):
    f = tmp_path / "a.html"
    f.write_text("<p>hello</p>")
    routes = course_routes()
    routes[("POST", "courses/77/discussion_topics")] = {"id": 5, "html_url": "u"}
    client, fake = client_for(routes)
    canvas.main(["announce", "--course-id", "77", "--file", str(f), "--title", "New",
                 "--apply"], client=client)
    (method, path, data), = fake.writes()
    assert data == {"title": "New", "message": "<p>hello</p>", "is_announcement": True}


def test_markdown_title_comes_from_the_h1(tmp_path):
    pytest.importorskip("shutil").which("pandoc") or pytest.skip("pandoc not installed")
    f = tmp_path / "a.md"
    f.write_text("# Lab 2 posted\n\nAccept it **now**.\n")
    title, html = canvas.render_body(f)
    assert title == "Lab 2 posted" and "<strong>now</strong>" in html and "Lab 2 posted" not in html


def test_discussion_is_unpublished_unless_asked(tmp_path):
    f = tmp_path / "d.html"
    f.write_text("<p>prompt</p>")
    routes = course_routes()
    routes[("POST", "courses/77/discussion_topics")] = {"id": 6}
    client, fake = client_for(routes)
    canvas.main(["discussion", "--course-id", "77", "--file", str(f), "--title", "Week 8",
                 "--apply"], client=client)
    assert fake.writes()[0][2]["published"] is False


def test_assignment_resolves_its_group_and_stays_unpublished():
    routes = course_routes()
    routes[("POST", "courses/77/assignments")] = {"id": 13, "name": "Lab 3"}
    client, fake = client_for(routes)
    canvas.main(["assignment", "--course-id", "77", "--name", "Lab 3", "--points", "100",
                 "--group", "assignments and labs", "--due", "2026-11-20T23:59:00-08:00",
                 "--apply"], client=client)
    body = fake.writes()[0][2]["assignment"]
    assert body["assignment_group_id"] == 2 and body["published"] is False
    assert body["submission_types"] == ["none"] and body["points_possible"] == 100


def test_syllabus_refuses_a_file_without_the_notes_serial(vault, tmp_path, capsys):
    note = vault / "classes" / "326" / "326-01-fa26.md"
    note.write_text(note.read_text().replace(
        "---\n\n#", "canvas:\n  course-id: 77\nsyllabus:\n  serial: 487BD388\n---\n\n#", 1))
    f = tmp_path / "syllabus_canvas.html"
    f.write_text("<p>no serial here</p>")
    client, fake = client_for({})
    rc = canvas.main(["syllabus", "--term", "fa26", "--vault-root", str(vault),
                      "--course", "CECS 326", "--section", "01", "--file", str(f), "--apply"],
                     client=client)
    assert rc == 2 and "487BD388" in capsys.readouterr().err and fake.writes() == []

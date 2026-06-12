from lectern.triage import load_roster_from_github_csv


def test_roster_join_maps_username_to_name(tmp_path):
    gh = tmp_path / "github.csv"
    gh.write_text("student_id,display_name,github_username\n"
                  "000000001,Harley Quinn,harley-quinn\n")
    roster = load_roster_from_github_csv(gh)
    assert roster["harley-quinn"]["display_name"] == "Harley Quinn"
    assert roster["harley-quinn"]["student_id"] == "000000001"


def test_init_writes_manifest_stub(tmp_path):
    from lectern.triage import main
    out = tmp_path / "lab02.triage.yaml"
    rc = main(["init", "--course", "CECS 326", "--name", "Lab 02",
               "--out", str(out), "--profile", "short-project"])
    assert rc == 0 and out.exists()
    import yaml
    cfg = yaml.safe_load(out.read_text())
    assert cfg["profile"] == "short-project"
    assert cfg["assignment"]["course"] == "CECS 326"


def test_sweep_writers_emit_csv_and_md(tmp_path):
    from lectern.triage import write_results_csv, write_triage_md
    rows = [
        {"name": "A", "repo_url": "u1", "triage": "FLAG",   "score": 10, "grade": "", "reasoning": "no deletions"},
        {"name": "B", "repo_url": "u2", "triage": "PASS",   "score": 90, "grade": "", "reasoning": "spread across 8 days"},
        {"name": "C", "repo_url": "u3", "triage": "REVIEW", "score": 50, "grade": "", "reasoning": "mixed"},
    ]
    cfg = {"assignment": {"name": "Lab 02"}, "schema_version": 1, "profile": "short-project"}
    csv_p = tmp_path / "results.csv"
    md_p = tmp_path / "TRIAGE.md"
    write_results_csv(rows, csv_p)
    write_triage_md(rows, md_p, cfg)

    body = md_p.read_text()
    # All three buckets present and in FLAG < REVIEW < PASS order
    assert body.index("FLAG") < body.index("REVIEW") < body.index("PASS")
    assert "Lab 02" in body and "schema_version" in body    # pinned footer

    csv_text = csv_p.read_text()
    assert csv_text.splitlines()[0] == "name,repo_url,triage,score,grade,reasoning"
    # CSV body is sorted: FLAG row before REVIEW row before PASS row
    assert csv_text.index("FLAG") < csv_text.index("REVIEW") < csv_text.index("PASS")


# ---------------------------------------------------------------------------
# Task 13 — reg-triage report subcommand
# ---------------------------------------------------------------------------

def test_report_subcommand_writes_md(tmp_path, mk_repo):
    from lectern.triage import main
    repo = mk_repo(tmp_path, [
        ("2026-05-16T01:48:00", {"a.c": "x"}),
        ("2026-05-20T14:19:00", {"a.c": "x", "Makefile": "all:"}),
    ])
    manifest = tmp_path / "m.triage.yaml"
    manifest.write_text(
        'assignment:\n'
        '  course: "CECS 326"\n  section: "99"\n  term: sp26\n  name: "Lab 02"\n'
        '  classroom_assignment_id: 0\n  org: Giacalone-CECS\n'
        '  repo_prefix: "cecs-326-sp26-99-lab-02-semaphores-"\n'
        '  assigned_date: 2026-03-12\n  due_date: 2026-05-16\n  total_points: 100\n'
        'profile: short-project\n'
        'deliverables:\n  - {name: makefile, match: makefile, required: true, auto_zero: true}\n'
    )
    gh = tmp_path / "github.csv"
    gh.write_text("student_id,display_name,github_username\n000000001,Harley Quinn,harley-quinn\n")
    out = tmp_path / "report.md"
    rc = main(["report", "harley-quinn", "--manifest", str(manifest), "--repo", str(repo),
               "--github-csv", str(gh), "--out", str(out)])
    assert rc == 0 and out.exists()
    body = out.read_text()
    assert "Part A" in body and "Part B" in body and "000000001" in body
    # the makefile is absent at the grading commit (due 2026-05-16, makefile added 05-20)
    assert "Harley Quinn" in body

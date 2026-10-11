from lectern._frontmatter import frontmatter


def test_single_course_dir(tmp_path):
    run = tmp_path / "classes" / "326" / "archives" / "fa26-01" / "recon-lab1"
    run.mkdir(parents=True)
    fm = frontmatter(run / "FACTS.md", note_type="lab-recon-facts", extra_tags=("lab",))
    assert fm.startswith("---\ntype: lab-recon-facts\n")
    assert "tags: [teaching, cecs-326, term-fa26, grading, lab, internal, private]" in fm
    assert fm.endswith("---\n\n")


def test_shared_dir_uses_class_note(tmp_path):
    classes = tmp_path / "classes" / "378-478"
    (classes / "archives" / "fa26-01" / "triage-lab1").mkdir(parents=True)
    (classes / "378-01-fa26.md").write_text("")
    fm = frontmatter(classes / "archives" / "fa26-01" / "triage-lab1" / "TRIAGE.md", note_type="lab-triage")
    assert "cecs-378" in fm and "cecs-478" not in fm and "term-fa26" in fm


def test_outside_vault_layout(tmp_path):
    fm = frontmatter(tmp_path / "REPORT.md", note_type="lab-report")
    assert "tags: [teaching, grading, internal, private]" in fm

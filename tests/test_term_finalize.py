import textwrap, yaml
from pathlib import Path
from lectern.term_finalize import main as fin_main
from lectern.vault_notes import split_frontmatter

def _section(V, cdir, num, sec, term, enrolled, letters):
    # class note
    cn = V / "classes" / cdir / f"{num}-{sec}-{term}.md"
    cn.parent.mkdir(parents=True, exist_ok=True)
    cn.write_text(
        f"---\ntype: class-note\ncourse: \"CECS {num}\"\ncourse-num: {num}\n"
        f"section: \"{sec}\"\nterm: \"{term}\"\nterm-name: \"Fall 2026\"\n"
        f"status: in-progress\nheadcount:\n  enrolled: {enrolled}\n  completed: 0\n  withdrew: 0\n"
        f"dfw-rate: 0\nupdated: 2026-01-01T00:00:00-08:00\n---\n# body\n## ☽ Reflection\nMINE\n")
    # bundle + gradebook.csv + manifest with STALE dist
    b = V / "classes" / cdir / "archives" / f"{term}-{sec}"
    b.mkdir(parents=True, exist_ok=True)
    rows = "student_id,display_name,weighted_score,letter_grade,enrollment_status\n" + \
        "".join(f"00{i},S{i},80,{l},active\n" for i, l in enumerate(letters))
    (b / "gradebook.csv").write_text(rows)
    man = {"course": f"CECS {num}", "term": term, "section": sec,
           "headcount": {"enrolled": enrolled, "completed": len(letters), "withdrew": 0},
           "grades": {"distribution": {"F": 99}, "dfw_rate": 1.0}, "audit": {}}
    (b / "manifest.yaml").write_text(yaml.safe_dump(man, sort_keys=False))
    return cn

def _vault(tmp_path):
    V = tmp_path / "vault"; (V / "classes").mkdir(parents=True)
    (V / "classes" / f"fa26.md").write_text(
        "---\ntype: semester-note\nterm: \"fa26\"\nterm-name: \"Fall 2026\"\n"
        "section-count: 1\ntotal-enrolled: 0\ntotal-completed: 0\noverall-dfw-rate: 0\n"
        "status: in-progress\nupdated: 2026-01-01T00:00:00-08:00\n---\n# Fall 2026\n## ☽ Term reflection\nMINE\n")
    return V

def test_finalize_reconciles_and_flips(tmp_path):
    V = _vault(tmp_path)
    _section(V, "326", "326", "01", "fa26", 4, ["A","B","B","C"])  # dfw=0
    assert fin_main(["--term", "fa26", "--vault-root", str(V)]) == 0
    man = yaml.safe_load((V/"classes"/"326"/"archives"/"fa26-01"/"manifest.yaml").read_text())
    assert man["grades"]["distribution"] == {"A":1,"B":2,"C":1}
    assert man["grades"]["dfw_rate"] == 0.0
    # backup of the reconciled manifest exists (dated)
    bak = list((V/"classes"/"326"/"archives"/"fa26-01").glob("manifest.yaml.bak-*"))
    assert len(bak) == 1
    fm, _ = split_frontmatter((V/"classes"/"326"/"326-01-fa26.md").read_text())
    assert fm["status"] == "finalized"
    sem, _b = split_frontmatter((V/"classes"/"fa26.md").read_text())
    assert sem["status"] == "finalized"
    assert sem["total-enrolled"] == 4
    # reflection body preserved
    assert "MINE" in (V/"classes"/"fa26.md").read_text()

def test_dry_run_writes_nothing(tmp_path):
    V = _vault(tmp_path)
    _section(V, "326", "326", "01", "fa26", 4, ["A","B","B","C"])
    before = (V/"classes"/"326"/"archives"/"fa26-01"/"manifest.yaml").read_text()
    assert fin_main(["--term","fa26","--vault-root",str(V),"--dry-run"]) == 0
    after = (V/"classes"/"326"/"archives"/"fa26-01"/"manifest.yaml").read_text()
    assert before == after
    fm, _ = split_frontmatter((V/"classes"/"326"/"326-01-fa26.md").read_text())
    assert fm["status"] == "in-progress"   # unchanged

def test_missing_gradebook_aborts(tmp_path):
    V = _vault(tmp_path)
    cn = _section(V, "326", "326", "01", "fa26", 4, ["A"])
    (V/"classes"/"326"/"archives"/"fa26-01"/"gradebook.csv").unlink()
    assert fin_main(["--term","fa26","--vault-root",str(V)]) == 1
    assert fin_main(["--term","fa26","--vault-root",str(V),"--allow-missing"]) == 0

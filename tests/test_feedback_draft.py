"""reg-lab-digest draft: opt-in LLM drafting, validated, with a deterministic verdict."""
import json
import sys
import textwrap
from pathlib import Path

from lectern import feedback_draft as fd
from lectern.digest_rubric import load_rubric
from lectern.lab_digest import main

RUBRIC = textwrap.dedent("""\
    lab: "Lab 1"
    total: 15
    sections:
      - {key: q1, label: "Q1 — The interleaving", max: 7}
      - {key: q2, label: "Q2 — Why the map survived", max: 5}
      - {key: q3, label: "Q3 — The timing", max: 3}
""")

# A fake model: echoes a reply chosen by the github_id it finds in the prompt.
FAKE = textwrap.dedent('''\
    import json, re, sys
    p = sys.stdin.read()
    gid = re.search(r'"github_id": "([^"]+)"', p.split("## Task", 1)[1]).group(1)
    sc = {"good": "You earned all 45 code points. Your trace shows both reads before both writes.",
          "dash": "Nice \\u2014 but this has an em dash.",
          "weak": "You earned 5 code points. Q1 needs an ordered trace."}[gid]
    secs = {"good": [7, 5, 2], "dash": [5, 5, 3], "weak": [2, 1, 0]}[gid]
    print(json.dumps({"github_id": gid, "sections": dict(zip(["q1", "q2", "q3"], secs)), "bonus": {},
                      "total": sum(secs), "comment": "note", "student_comment": sc,
                      "confidence": "high" if gid == "good" else "medium", "abstain": False}))
''')


def _bundle(tmp_path):
    b = tmp_path / "recon"
    (b / "repos").mkdir(parents=True); (b / "writeups").mkdir()
    pts = {"good": 45, "dash": 45, "weak": 5}
    for gid, p in pts.items():
        ch = {"build": {"passed": True}, "map": {"passed": p == 45}}
        (b / "repos" / f"{gid}.json").write_text(json.dumps(
            {"github_id": gid, "student": gid, "autograde": {"points": p, "max": 45, "honor_ok": True, "challenges": ch}}))
        (b / "writeups" / f"{gid}.md").write_text("Q1: A reads 40, B reads 40, both write 41.")
    (b / "cohort.csv").write_text("github_id,student,points\n" + "".join(f"{g},{g},{p}\n" for g, p in pts.items()))
    (tmp_path / "r.yaml").write_text(RUBRIC)
    (tmp_path / "doctrine.md").write_text("# Feedback doctrine\nFour steps.")
    (tmp_path / "fake.py").write_text(FAKE)
    return b


def test_draft_is_off_unless_enabled(tmp_path, monkeypatch, capsys):
    b = _bundle(tmp_path)
    monkeypatch.setattr(fd, "CONFIG", tmp_path / "none.toml")
    rc = main(["draft", "--bundle", str(b), "--rubric", str(tmp_path / "r.yaml"),
               "--doctrine", str(tmp_path / "doctrine.md")])
    assert rc == 2 and "off" in capsys.readouterr().out
    assert not (b / "digest_results.jsonl").exists()


def test_draft_validates_appends_verdicts_and_summarises(tmp_path):
    b = _bundle(tmp_path)
    rc = main(["draft", "--enable", "--bundle", str(b), "--rubric", str(tmp_path / "r.yaml"),
               "--doctrine", str(tmp_path / "doctrine.md"), "--jobs", "1",
               "--llm-cmd", f"{sys.executable} {tmp_path / 'fake.py'}"])
    assert rc == 0
    res = {json.loads(l)["github_id"]: json.loads(l) for l in (b / "digest_results.jsonl").read_text().splitlines()}
    assert res["good"]["student_comment"].endswith("Excellent work.")       # 45 + 14 = 59 of 60
    assert res["dash"]["abstain"] is True and "em dash" in res["dash"]["comment"]
    assert "office hours" in res["weak"]["student_comment"]
    assert "map" in res["weak"]["student_comment"]                       # failed check named first
    summary = (b / "DRAFTS.md").read_text()
    assert "Needs a human read" in summary and "dash" in summary


def test_verdict_ladder():
    assert fd.verdict(60, 60, "x") == "Excellent work."
    assert fd.verdict(56, 60, "x") == "Strong work."
    assert fd.verdict(51, 60, "Q3") == "Solid work; tighten Q3 next time."
    assert "office hours" in fd.verdict(30, 60, "the timing")
    assert fd.with_verdict("Great trace. Excellent work.", 30, 60, "x") == "Great trace. Excellent work."


def test_weakest_area_uses_lab_terms(tmp_path):
    (tmp_path / "r.yaml").write_text(RUBRIC)
    r = load_rubric(tmp_path / "r.yaml")
    assert fd.weakest_area({"q1": 7, "q2": 5, "q3": 0}, r, []) == "the timing"
    assert fd.weakest_area({"q1": 7}, r, ["map"]) == "map"


def test_prompt_carries_a_factual_report(tmp_path):
    b = _bundle(tmp_path)
    facts = fd.fact_sheet(b, "weak", {"map": "assembling the map"})
    assert "Autograde: 5 / 45" in facts
    assert "assembling the map: FAILED" in facts and "build: passed" in facts
    assert "triage" not in facts.lower()
    p = fd._prompt({"github_id": "weak", "schema": {}}, "doc", "contract", None, facts)
    assert "## Facts" in p and "only what these facts and the writeup support" in p

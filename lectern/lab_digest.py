"""reg-lab-digest — emit a grading work-list / merge graded results (advisory, deterministic)."""
from __future__ import annotations
import argparse
from pathlib import Path
from lectern.digest_rubric import load_rubric
from lectern.digest_emit import emit
from lectern.digest_merge import merge_results, apply_to_cohort

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="reg-lab-digest",
        description="Layer-2 writeup digest: emit a grading work-list, merge graded results.")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("emit"); e.add_argument("--bundle", type=Path, required=True)
    e.add_argument("--rubric", type=Path, required=True); e.add_argument("--out", type=Path, required=True)
    m = sub.add_parser("merge"); m.add_argument("--bundle", type=Path, required=True)
    m.add_argument("--rubric", type=Path, required=True); m.add_argument("--results", type=Path, required=True)
    d = sub.add_parser("draft", help="LLM-draft feedback for every task (optional; off by default)")
    d.add_argument("--bundle", type=Path, required=True)
    d.add_argument("--rubric", type=Path, required=True)
    d.add_argument("--doctrine", type=Path, help="feedback-doctrine.md (default: config)")
    d.add_argument("--llm-cmd", help="command reading the prompt on stdin (default: config)")
    d.add_argument("--jobs", type=int, default=4)
    d.add_argument("--manifest", type=Path, help="report manifest: also render REPORT.md")
    d.add_argument("--enable", action="store_true",
                   help="run even if [feedback_drafts] enabled is not set in the lectern config")
    a = p.parse_args(argv)
    rubric = load_rubric(a.rubric)
    if a.cmd == "draft":
        return _draft(a, rubric)
    if a.cmd == "emit":
        n = emit(a.bundle, rubric, a.out)
        print(f"digest: {n} task(s) to grade -> {a.out}")
        return 0
    merged = list(merge_results(a.bundle, rubric, a.results))
    apply_to_cohort(a.bundle, merged)
    scored = sum(1 for x in merged if x.score is not None)
    held = sum(1 for x in merged if x.score is None)
    print(f"digest: merged {scored} scored, {held} withheld -> {a.bundle}/cohort.csv")
    return 0

def _draft(a, rubric) -> int:
    from lectern import feedback_draft as fd
    cfg = fd.load_config()
    if not (a.enable or cfg.get("enabled")):
        print("reg-lab-digest draft: off. It calls a language model, so it runs only when "
              f"[feedback_drafts] enabled = true in {fd.CONFIG} or with --enable.")
        return 2
    llm = a.llm_cmd or cfg.get("llm_cmd") or "claude -p"
    doctrine = a.doctrine or (Path(cfg["doctrine"]).expanduser() if cfg.get("doctrine") else None)
    if not doctrine or not doctrine.is_file():
        print(f"reg-lab-digest draft: feedback doctrine not found ({doctrine}); pass --doctrine")
        return 2
    tasks = a.bundle / "digest_tasks.jsonl"
    n = emit(a.bundle, rubric, tasks)
    print(f"draft: {n} task(s); drafting with `{llm}` ({a.jobs} at a time)")
    results_path = a.bundle / "digest_results.jsonl"
    results = fd.draft_bundle(a.bundle, rubric, tasks, results_path, doctrine_path=doctrine,
                              llm_cmd=llm, jobs=a.jobs, check_labels=cfg.get("check_labels"))
    merged = list(merge_results(a.bundle, rubric, results_path))
    apply_to_cohort(a.bundle, merged)
    fd.write_summary(a.bundle, results, a.bundle / "DRAFTS.md")
    held = sum(1 for x in merged if x.score is None)
    print(f"draft: {len(merged) - held} drafted, {held} need a human read -> "
          f"{a.bundle}/cohort.csv, review guide {a.bundle}/DRAFTS.md")
    if a.manifest:
        from lectern.lab_report import main as report_main
        report_main(["render", "--bundle", str(a.bundle), "--cohort", str(a.bundle / "cohort.csv"),
                     "--manifest", str(a.manifest), "--out", str(a.bundle / "REPORT.md")])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

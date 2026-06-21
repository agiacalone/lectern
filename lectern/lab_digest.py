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
    a = p.parse_args(argv)
    rubric = load_rubric(a.rubric)
    if a.cmd == "emit":
        n = emit(a.bundle, rubric, a.out)
        print(f"digest: {n} task(s) to grade -> {a.out}")
        return 0
    merged = merge_results(a.bundle, rubric, a.results)
    apply_to_cohort(a.bundle, merged)
    scored = sum(1 for x in merged if x.score is not None)
    held = sum(1 for x in merged if x.score is None)
    print(f"digest: merged {scored} scored, {held} withheld -> {a.bundle}/cohort.csv")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

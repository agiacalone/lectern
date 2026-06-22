"""Deliver sanitized, GPG-signed feedback to each student's repo feedback branch.

Outward-facing + hard-to-reverse, so:
  * --dry-run is the DEFAULT (deliver(execute=False)): no remote ops, just a plan.
  * signing is MANDATORY: refuses to push an unsigned commit.
  * idempotent: skips repos whose FEEDBACK.md already matches.
All git/gh calls go through injected callbacks (mockable in tests).
"""
import os
import subprocess


def _sh(*args, **k):
    return subprocess.run(args, capture_output=True, text=True, **k)


def _grand(m):
    return m.auto_max + m.writeup_max


def render_feedback_md(row, manifest) -> str:
    total = row["points"] + row["writeup_score"]
    if not row.get("honor_ok", True) or total == 0:
        comment = ("No submission was recorded for this lab. If you believe this is an "
                   "error, please contact me right away.")
    else:
        comment = row.get("student_comment") or "_See the score breakdown above._"
    return (f"# {manifest.lab} — Feedback\n\n"
            f"**Total: {total} / {_grand(manifest)}**\n\n"
            f"| Component | Score |\n| --- | --: |\n"
            f"| Wards (autograder) | {row['points']} / {manifest.auto_max} |\n"
            f"| Grimoire (writeup) | {row['writeup_score']} / {manifest.writeup_max} |\n\n"
            f"## Comments\n{comment}\n\n---\n"
            f"*{manifest.course} · {manifest.term} · §{manifest.section} — graded by Prof. Giacalone*\n")


def deliver(cohort, manifest, workdir, *, execute=False, close=True,
            only=None, skip=None, gh=_sh, git=_sh):
    rows = [r for r in cohort
            if (not only or r["github_id"] in only) and (not skip or r["github_id"] not in skip)]
    entries = []
    for r in rows:
        gid = r["github_id"]
        repo = f"{manifest.org}/{manifest.repo_prefix}-{gid}"
        total = r["points"] + r["writeup_score"]
        md = render_feedback_md(r, manifest)
        posted = signed = False
        pr_state = "-"
        if execute:
            dest = os.path.join(workdir, gid)
            gh("repo", "clone", repo, dest, "--", "--branch",
               manifest.feedback_branch, "--single-branch")
            fb = os.path.join(dest, "FEEDBACK.md")
            existing = open(fb).read() if os.path.exists(fb) else None
            if existing == md:
                pr_state = "unchanged"
            else:
                with open(fb, "w") as f:
                    f.write(md)
                git("-C", dest, "add", "FEEDBACK.md")
                git("-C", dest, "commit", "-S", "-m", "Lab feedback and grade breakdown")
                ver = git("-C", dest, "log", "-1", "--show-signature")
                blob = (getattr(ver, "stdout", "") or "") + (getattr(ver, "stderr", "") or "")
                signed = "Good signature" in blob
                if not signed:
                    raise RuntimeError(f"refusing to push unsigned commit for {gid}")
                git("-C", dest, "push", "origin", manifest.feedback_branch)
                posted = True
                st = gh("pr", "view", str(manifest.feedback_pr), "--repo", repo,
                        "--json", "state", "-q", ".state")
                pr_state = (getattr(st, "stdout", "") or "").strip() or "-"
                if close and pr_state == "OPEN":
                    gh("pr", "close", str(manifest.feedback_pr), "--repo", repo)
                    pr_state = "CLOSED"
        entries.append({"github_id": gid, "student": r["student"], "auto": r["points"],
                        "writeup": r["writeup_score"], "total": total,
                        "student_comment": r.get("student_comment", ""),
                        "posted": posted, "signed": signed, "pr_state": pr_state})
    return entries


def main(argv=None):
    import argparse
    import csv
    from lectern.report_manifest import load_report_manifest
    from lectern.feedback_log import render_feedback_log
    ap = argparse.ArgumentParser(prog="reg-lab-report deliver")
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--workdir", default="/tmp/reg-lab-report")
    ap.add_argument("--execute", action="store_true",
                    help="perform remote ops (default is dry-run)")
    ap.add_argument("--no-close", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--skip", nargs="*")
    ap.add_argument("--log-out")
    a = ap.parse_args(argv)
    m = load_report_manifest(a.manifest)
    with open(a.cohort) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["points"] = int(float(r.get("points") or 0))
        r["writeup_score"] = int(float(r.get("writeup_score") or 0))
        r["honor_ok"] = str(r.get("honor_ok")).lower() in ("true", "1", "yes")
    os.makedirs(a.workdir, exist_ok=True)
    entries = deliver(rows, m, a.workdir, execute=a.execute, close=not a.no_close,
                      only=a.only, skip=a.skip)
    if a.log_out:
        with open(a.log_out, "w") as f:
            f.write(render_feedback_log(entries, m) + "\n")
    print(("EXECUTED" if a.execute else "DRY-RUN") + f": {len(entries)} repos")
    return 0

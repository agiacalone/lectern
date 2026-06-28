"""Deliver sanitized, GPG-signed feedback to each student's repo.

Outward-facing + hard-to-reverse, so:
  * --dry-run is the DEFAULT (deliver(execute=False)): no remote ops, just a plan.
  * signing is MANDATORY: refuses to push an unsigned commit (feedback OR merge).
  * idempotent: skips repos whose FEEDBACK.md already matches — independently on
    the feedback branch and on main.

Delivery is two-stage per repo:
  1. commit FEEDBACK.md to the `feedback` branch + close the Classroom feedback PR;
  2. merge `feedback` into `main` (default branch) so FEEDBACK.md is visible on the
     student's default branch. Classroom repos with an unrelated `main`/`feedback`
     history (no common ancestor) can't be merged, so the file is landed directly
     on main with a signed commit instead.

All git/gh calls go through injected callbacks (mockable in tests).
"""
import os
import subprocess

MERGE_MSG = "Merge feedback branch: add FEEDBACK.md (grade + comments)"
_ADD_MSG = "Add FEEDBACK.md (grade + comments)"


def _sh(*args, **k):
    return subprocess.run(args, capture_output=True, text=True, **k)


def _gh(*a, **k):
    return _sh("gh", *a, **k)


def _git(*a, **k):
    return _sh("git", *a, **k)


def _grand(m):
    return m.auto_max + m.writeup_max


def _blob(res):
    return (getattr(res, "stdout", "") or "") + (getattr(res, "stderr", "") or "")


def _is_signed(git, dest):
    return "Good signature" in _blob(git("-C", dest, "log", "-1", "--show-signature"))


_NO_SUBMISSION = ("No submission was recorded for this lab. If you believe this is an "
                  "error, please contact me right away.")


def render_feedback_md(row, manifest) -> str:
    total = row["points"] + row["writeup_score"]
    if not row.get("honor_ok", True) or total == 0:
        comment = _NO_SUBMISSION
    else:
        comment = row.get("student_comment") or "_See the score breakdown above._"
    return (f"# {manifest.lab} — Feedback\n\n"
            f"**Total: {total} / {_grand(manifest)}**\n\n"
            f"| Component | Score |\n| --- | --: |\n"
            f"| Wards (autograder) | {row['points']} / {manifest.auto_max} |\n"
            f"| Grimoire (writeup) | {row['writeup_score']} / {manifest.writeup_max} |\n\n"
            f"## Comments\n{comment}\n\n---\n"
            f"*{manifest.course} · {manifest.term} · §{manifest.section} — graded by Prof. Giacalone*\n")


def render_feedback_md_from_note(row, manifest) -> str:
    """Render FEEDBACK.md from a note-authored row (N generic components).

    The vault note is the source of truth; this renders the same student-facing
    shape as render_feedback_md but over an arbitrary component list parsed from
    the note (see lectern.feedback_note).
    """
    total, grand = row["total"], row["grand"]
    comment = _NO_SUBMISSION if total == 0 else (row.get("comment") or "_See the score breakdown above._")
    lines = [f"# {manifest.lab} — Feedback", "", f"**Total: {total} / {grand}**", "",
             "| Component | Score |", "| --- | --: |"]
    for c in row["components"]:
        label = c["label"] + (" (extra credit)" if c.get("ec") else "")
        score = c["score"] if c["score"] is not None else 0
        score_s = f"+{score}" if c.get("ec") else f"{score}"
        lines.append(f"| {label} | {score_s} / {c['max']} |")
    lines += ["", "## Comments", comment, "", "---",
              f"*{manifest.course} · {manifest.term} · §{manifest.section} — graded by Prof. Giacalone*", ""]
    return "\n".join(lines)


def _merge_to_main(git, dest, manifest, md):
    """Land FEEDBACK.md on the default branch. Returns a state string.

    Prefers a signed merge of the feedback branch; falls back to a signed direct
    add when the histories are unrelated (Classroom repos rebuilt main from scratch).
    Idempotent: a no-op when main already carries the exact file.
    """
    branch = manifest.default_branch
    git("-C", dest, "checkout", branch)
    probe = git("-C", dest, "show", f"{branch}:FEEDBACK.md")
    if getattr(probe, "returncode", 0) == 0 and (getattr(probe, "stdout", "") or "") == md:
        return "unchanged"
    res = git("-C", dest, "merge", "--no-ff", "--no-edit", "-S",
              manifest.feedback_branch, "-m", MERGE_MSG)
    body = _blob(res)
    unrelated = "unrelated histories" in body or "refusing to merge" in body
    if getattr(res, "returncode", 0) == 0 and not unrelated:
        if not _is_signed(git, dest):
            raise RuntimeError("refusing to push unsigned merge to main")
        git("-C", dest, "push", "origin", branch)
        return "merged"
    # unrelated history: commit the file straight onto main
    with open(os.path.join(dest, "FEEDBACK.md"), "w") as f:
        f.write(md)
    git("-C", dest, "add", "FEEDBACK.md")
    git("-C", dest, "commit", "-S", "-m", _ADD_MSG)
    if not _is_signed(git, dest):
        raise RuntimeError("refusing to push unsigned commit to main")
    git("-C", dest, "push", "origin", branch)
    return "added"


def deliver(cohort, manifest, workdir, *, execute=False, close=True, merge_main=True,
            only=None, skip=None, render=render_feedback_md, gh=_gh, git=_git):
    rows = [r for r in cohort
            if (not only or r["github_id"] in only) and (not skip or r["github_id"] not in skip)]
    entries = []
    for r in rows:
        gid = r["github_id"]
        repo = f"{manifest.org}/{manifest.repo_prefix}-{gid}"
        total = r["total"] if "total" in r else r["points"] + r["writeup_score"]
        md = render(r, manifest)
        posted = signed = False
        pr_state, main_state = "-", "-"
        if execute:
            dest = os.path.join(workdir, gid)
            gh("repo", "clone", repo, dest)          # full clone: both branches present
            git("-C", dest, "checkout", manifest.feedback_branch)
            fb = os.path.join(dest, "FEEDBACK.md")
            existing = open(fb).read() if os.path.exists(fb) else None
            if existing == md:
                pr_state = "unchanged"
            else:
                with open(fb, "w") as f:
                    f.write(md)
                git("-C", dest, "add", "FEEDBACK.md")
                git("-C", dest, "commit", "-S", "-m", "Lab feedback and grade breakdown")
                signed = _is_signed(git, dest)
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
            # merge onto main regardless of feedback-branch idempotency: the file may
            # already be on feedback yet still missing from the student's default branch.
            if merge_main:
                main_state = _merge_to_main(git, dest, manifest, md)
                signed = signed or main_state in ("merged", "added")
        entries.append({"github_id": gid, "student": r["student"],
                        "auto": r.get("points"), "writeup": r.get("writeup_score"),
                        "total": total, "grand": r.get("grand"),
                        "components": r.get("components"),
                        "student_comment": r.get("student_comment") or r.get("comment", ""),
                        "posted": posted, "signed": signed,
                        "pr_state": pr_state, "main_state": main_state})
    return entries


def main(argv=None):
    import argparse
    import csv
    from lectern.report_manifest import load_report_manifest
    from lectern.feedback_log import render_feedback_log
    ap = argparse.ArgumentParser(prog="reg-lab-report deliver")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--cohort", help="digest-merged cohort.csv (digest path)")
    src.add_argument("--from-note", dest="from_note",
                     help="the grading-round REPORT.md (note-authoritative path)")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--workdir", default="/tmp/reg-lab-report")
    ap.add_argument("--execute", action="store_true",
                    help="perform remote ops (default is dry-run)")
    ap.add_argument("--no-close", action="store_true")
    ap.add_argument("--no-merge-main", action="store_true",
                    help="skip merging the feedback branch into main")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--skip", nargs="*")
    ap.add_argument("--log-out")
    a = ap.parse_args(argv)
    m = load_report_manifest(a.manifest)
    if a.from_note:
        from lectern.feedback_note import parse_feedback_note
        rows = [r for r in parse_feedback_note(a.from_note) if r["graded"]]
        render = render_feedback_md_from_note
    else:
        with open(a.cohort) as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r["points"] = int(float(r.get("points") or 0))
            r["writeup_score"] = int(float(r.get("writeup_score") or 0))
            r["honor_ok"] = str(r.get("honor_ok")).lower() in ("true", "1", "yes")
        render = render_feedback_md
    os.makedirs(a.workdir, exist_ok=True)
    entries = deliver(rows, m, a.workdir, execute=a.execute, close=not a.no_close,
                      merge_main=not a.no_merge_main, only=a.only, skip=a.skip, render=render)
    if a.log_out:
        with open(a.log_out, "w") as f:
            f.write(render_feedback_log(entries, m) + "\n")
    print(("EXECUTED" if a.execute else "DRY-RUN") + f": {len(entries)} repos")
    return 0

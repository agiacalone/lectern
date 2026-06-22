"""Render the verbatim feedback-delivery record (FEEDBACK_LOG.md).

The disputable record: the exact student-facing text delivered, plus per-repo
signature + PR status. Score-ordered. Private (instructor record).
"""


def render_feedback_log(entries, manifest) -> str:
    grand = manifest.auto_max + manifest.writeup_max
    out = ["---", "type: feedback-log",
           "tags: [feedback-log, grading, private]", "visibility: private",
           "icon: LiMessageSquareText", "iconColor: var(--text-normal)", "---",
           f"# {manifest.lab} · Feedback Delivered to Students",
           f"*{manifest.course} · {manifest.term} · §{manifest.section} — verbatim record*", ""]
    for e in sorted(entries, key=lambda e: -e["total"]):
        sig = "signed ✓" if e.get("signed") else "UNSIGNED"
        out.append(f"### {e['student']} — {e['total']}/{grand}")
        out.append(f"*github: `{e['github_id']}` · Auto {e['auto']}/{manifest.auto_max} · "
                   f"Writeup {e['writeup']}/{manifest.writeup_max} · {sig} · PR {e.get('pr_state', '-')}*")
        out.append("")
        out.append(f"> {e.get('student_comment') or '_no comment_'}")
        out.append("")
    return "\n".join(out)

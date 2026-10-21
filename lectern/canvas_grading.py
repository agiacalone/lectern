"""Gradebook audit and discussion grading for ``reg-canvas``.

Two jobs that read a course's gradebook as a whole, kept apart from
:mod:`lectern.canvas` so that module stays a thin set of export/push verbs:

- :func:`cmd_audit` finds work that was never graded or never posted, plus
  settings that skew the weighted score: an empty weighted group (the sign an
  exam was filed in the wrong one), and a missing-submission policy that is
  off, which leaves non-posters blank where Canvas's current score skips them.
- :func:`cmd_discussions` grades the weekly discussion assignments by post
  count. ``review`` builds the short list a human has to look at; ``apply``
  writes scores and likes, a dry run until ``--apply``.

Discussion posts are read to *measure* them, the same reading an instructor
does in SpeedGrader. The text is reduced to the numbers in :func:`metrics`
as each topic arrives and is never written, printed or kept. What reaches
disk is names, Canvas ids, entry ids and those numbers, in a mode-700 workdir
(and, with ``--note``, a vault note) that the instructor deletes after use.

The metrics are prompts to read a post, not a verdict. In particular they
are **not** an AI detector: detectors have high false-positive rates, above
all for students writing in a second language. ``max_overlap`` is a fact
(shared five-word phrases with another student's post), not a judgement.
"""
from __future__ import annotations

import csv
import html
import io
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from lectern.canvas_api import CanvasClient

# Points for 2+, 1 and 0 credited posts. Missing work is already 0 through
# the course's missing-submission policy, so 0 is only ever a denial.
FULL, PARTIAL = 5, 3
SHORT_WORDS = 25    # a post under this goes on the review list
OVERLAP = 0.30      # max_overlap at or above this goes on the review list
SHINGLE = 5         # words per phrase for max_overlap


class GradingError(Exception):
    """A user-facing failure of ``audit`` or ``discussions``."""


# ── who counts ───────────────────────────────────────────────────────────────


def section_key(target) -> str:
    """``326-01`` for a vault target; the Canvas course id otherwise."""
    sec = target.section or {}
    if sec.get("course") and sec.get("section"):
        return f"{str(sec['course']).split()[-1]}-{sec['section']}"
    return str(target.course_id)


def scoped(values: list[str] | None, target) -> set[str]:
    """SIS ids from ``SIS`` (every section) or ``SIS@KEY`` (one section) arguments.

    ``KEY`` is :func:`section_key` (``326-03``) or a Canvas course id.
    """
    keys = {section_key(target), str(target.course_id)}
    out = set()
    for v in values or []:
        sis, _, where = v.partition("@")
        if not where or where in keys:
            out.add(sis)
    return out


def students(client: CanvasClient, course_id: int, exclude: set[str]) -> dict[int, dict]:
    """Active student enrolments, keyed by Canvas user id, minus ``exclude`` SIS ids."""
    out = {}
    for e in client.get_all(f"courses/{course_id}/enrollments",
                            [("type[]", "StudentEnrollment"), ("state[]", "active")]):
        u = e.get("user") or {}
        if u.get("sis_user_id") in exclude:
            continue
        out[e["user_id"]] = {"name": u.get("sortable_name") or "?",
                             "sis": u.get("sis_user_id") or "",
                             "grades": e.get("grades") or {}}
    return out


# Score fields only, as in canvas.SCORE_FIELDS, plus the posting and timing
# fields the audit needs. Submission content is never kept.
AUDIT_FIELDS = ("user_id", "assignment_id", "score", "excused", "missing",
                "workflow_state", "posted_at", "submitted_at")


def _ts(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


# ── audit ────────────────────────────────────────────────────────────────────


def audit_course(client: CanvasClient, course_id: int, exclude: set[str],
                 now: datetime | None = None) -> tuple[list[str], int]:
    """The report lines for one course, and how many problems it found."""
    now = now or datetime.now(timezone.utc)
    lines, problems = [], 0
    course = client.get(f"courses/{course_id}")
    weighted = bool(course.get("apply_assignment_group_weights"))
    groups = list(client.get_all(f"courses/{course_id}/assignment_groups"))
    assigns = list(client.get_all(f"courses/{course_id}/assignments"))
    per_group = Counter(a.get("assignment_group_id") for a in assigns)
    gname = {g["id"]: g["name"] for g in groups}

    lines.append(f"Groups ({'weighted' if weighted else 'not weighted'}):")
    total = 0.0
    for g in groups:
        w = g.get("group_weight") or 0
        total += w
        n = per_group.get(g["id"], 0)
        flag = ""
        if weighted and w and not n:
            flag = "  <- weighted but empty: is an assignment in the wrong group?"
            problems += 1
        lines.append(f"  {g['name']:<30} {w:>5g}%  {n} assignment(s){flag}")
    if weighted and abs(total - 100) > 0.01:
        lines.append(f"  weights sum to {total:g}, not 100")
        problems += 1

    policy = (client.get(f"courses/{course_id}/late_policy") or {}).get("late_policy") or {}
    if not policy.get("missing_submission_deduction_enabled"):
        lines.append("Missing-submission policy is OFF: non-posters stay blank, and the "
                     "current score skips blanks.")
        problems += 1

    studs = students(client, course_id, exclude)
    subs: dict[int, dict[int, dict]] = defaultdict(dict)
    for s in client.get_all(f"courses/{course_id}/students/submissions",
                            [("student_ids[]", "all")]):
        k = {f: s.get(f) for f in AUDIT_FIELDS}
        if k["user_id"] in studs:
            subs[k["assignment_id"]][k["user_id"]] = k

    for t, n in Counter(a["name"] for a in assigns).items():
        if n > 1:
            lines.append(f"Duplicate assignment name: {t!r} x{n}")
            problems += 1

    lines.append(f"Assignments ({len(studs)} active students):")
    order = sorted(assigns, key=lambda a: (gname.get(a.get("assignment_group_id"), ""),
                                           a.get("position") or 0))
    for a in order:
        rows = subs.get(a["id"], {})
        graded = [r for r in rows.values() if r["score"] is not None or r["excused"]]
        hidden = [r for r in graded if not r["posted_at"]]
        waiting = [r for r in rows.values()
                   if r["workflow_state"] in ("submitted", "pending_review") and r["score"] is None]
        due = _ts(a.get("due_at"))
        flags = []
        if not a.get("published"):
            flags.append("unpublished")
        if due and due < now and a.get("published") and len(graded) < len(studs):
            flags.append(f"past due, {len(studs) - len(graded)} ungraded")
        if waiting:
            flags.append(f"{len(waiting)} submitted, not graded")
        if hidden:
            zeros = sum(1 for r in hidden if r["score"] == 0 and r["missing"])
            flags.append(f"{len(hidden)} graded but hidden"
                         + (f" ({zeros} are missing-work zeros)" if zeros else ""))
        problems += bool(flags)
        lines.append(f"  [{gname.get(a.get('assignment_group_id'), '?')[:18]:<18}] "
                     f"{a['name'][:40]:<40} graded {len(graded):>3}/{len(studs)}"
                     + (f"  <- {'; '.join(flags)}" if flags else ""))

    drift = [s["name"] for s in studs.values()
             if s["grades"].get("current_score") != s["grades"].get("unposted_current_score")]
    if drift:
        lines.append(f"{len(drift)} student(s) see a score that differs from their score "
                     "with hidden grades included. Posting will change it.")
    return lines, problems


def cmd_audit(client: CanvasClient, args, targets) -> int:
    found = 0
    for t in targets:
        lines, n = audit_course(client, t.course_id, scoped(args.exclude_sis, t))
        print(f"== {t.label} (course {t.course_id})")
        print("\n".join(lines))
        print()
        found += n
    return 1 if found else 0


# ── discussion metrics ───────────────────────────────────────────────────────


def plain(message: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", message or ""))


def _syllables(word: str) -> int:
    w = word.lower()
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups) - (1 if w.endswith("e") and len(groups) > 1 else 0)
    return max(n, 1)


def metrics(message: str | None, classmates: set[str]) -> dict:
    """Facts about one post's writing. The text itself is not returned.

    ``fk_grade`` is the Flesch-Kincaid grade level. ``sent_len_sd`` is the
    spread of sentence lengths (low means a uniform rhythm). ``vocab_ratio``
    is distinct words over total words. ``_shingles`` is consumed by
    :func:`add_overlap` and removed before anything is written.
    """
    text = plain(message)
    toks = re.findall(r"[A-Za-z']+", text)
    sents = [s for s in re.split(r"[.!?]+\s", text) if s.strip()] or [text]
    lens = [len(s.split()) for s in sents]
    n = len(toks) or 1
    mean = sum(lens) / len(lens)
    lower = [t.lower() for t in toks]
    return {
        "words": len(toks),
        "fk_grade": round(0.39 * n / len(sents) + 11.8 * sum(map(_syllables, toks)) / n - 15.59, 1),
        "sent_len_sd": round((sum((x - mean) ** 2 for x in lens) / len(lens)) ** 0.5, 1),
        "vocab_ratio": round(len(set(lower)) / n, 2),
        "links": len(re.findall(r"https?://", message or "")),
        "code": bool(re.search(r"<(pre|code)\b", message or "")),
        "names_classmate": any(re.search(rf"\b{re.escape(f)}\b", text) for f in classmates),
        "_shingles": {tuple(lower[i:i + SHINGLE]) for i in range(len(lower) - SHINGLE + 1)},
    }


def first_name(sortable: str) -> str | None:
    if ", " not in sortable:
        return None
    rest = sortable.split(", ", 1)[1].split()
    return rest[0] if rest else None


def topic_posts(view: dict, first_names: dict[int, str]) -> list[tuple[int, int, dict]]:
    """``(user_id, entry_id, metrics)`` for every live entry in a topic view."""
    names = set(first_names.values())
    out: list[tuple[int, int, dict]] = []

    def walk(entries, parent):
        for e in entries or []:
            if not e.get("deleted"):
                m = metrics(e.get("message"), names - {first_names.get(e["user_id"])})
                m["reply"] = parent is not None
                m["got_replies"] = sum(1 for r in e.get("replies") or [] if not r.get("deleted"))
                out.append((e["user_id"], e["id"], m))
            walk(e.get("replies"), e["id"])

    walk((view or {}).get("view"), None)
    add_overlap(out)
    return out


def add_overlap(posts: list[tuple[int, int, dict]]) -> None:
    """Set ``max_overlap``: the largest share of a post's phrases in another student's post."""
    for uid, _, m in posts:
        best = 0.0
        for uid2, _, m2 in posts:
            if uid2 != uid and m["_shingles"] and m2["_shingles"]:
                best = max(best, len(m["_shingles"] & m2["_shingles"]) / len(m["_shingles"]))
        m["max_overlap"] = round(best, 2)
    for _, _, m in posts:
        del m["_shingles"]


def describe(m: dict) -> str:
    bits = [f"{m['words']} words", f"grade {m['fk_grade']}", f"rhythm sd {m['sent_len_sd']}",
            "reply" if m["reply"] else "top-level"]
    if m["got_replies"]:
        bits.append(f"{m['got_replies']} replies")
    if m["names_classmate"]:
        bits.append("names a classmate")
    if m["links"]:
        bits.append(f"{m['links']} links")
    if m["code"]:
        bits.append("code")
    if m["max_overlap"] >= OVERLAP:
        bits.append(f"OVERLAP {m['max_overlap']:.0%}")
    return ", ".join(bits)


def score_for(credited: int, full_credit: bool) -> int:
    return FULL if full_credit or credited >= 2 else PARTIAL if credited else 0


# ── discussions review / apply ───────────────────────────────────────────────


def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _private_write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


_WEEK = re.compile(r"^(Week \d+)\b")


def week_of(name: str, wanted: list[str] | None) -> str | None:
    """The week an assignment belongs to: a ``--week`` prefix, or its own ``Week N``."""
    if wanted:
        return next((w for w in wanted if name.startswith(w)), None)
    m = _WEEK.match(name)
    return m.group(1) if m else None


def _week_order(week: str):
    m = re.search(r"\d+", week)
    return (int(m.group()) if m else 0, week)


def default_note(vault: Path, term: str, weeks: list[str] | None = None) -> Path:
    if not weeks:  # the term's running report, one section per week
        return vault / "classes" / "semesters" / f"{term}-discussions-grading.md"
    slug = "-".join(re.sub(r"[^a-z0-9]+", "", w.lower()).replace("week", "w") for w in weeks)
    return vault / "classes" / "semesters" / f"{term}-discussions-{slug}-grading.md"


def review(client: CanvasClient, args, targets) -> int:
    wd = _private_dir(Path(args.workdir).expanduser())
    plan, rows = [], []
    flagged: dict[str, list[str]] = defaultdict(list)
    summary: dict[str, list[str]] = defaultdict(list)
    note = note_path(args)
    # A rerun refreshes the note and keeps every deny already ticked in it, so
    # the review can run mid-week and again after the due date.
    kept = set() if args.force or not note else denials(wd, note) - _file_denials(wd)
    for t in targets:
        studs = students(client, t.course_id, scoped(args.exclude_sis, t))
        full = scoped(args.full_credit_sis, t)
        firsts = {uid: first_name(s["name"]) for uid, s in studs.items()}
        firsts = {k: v for k, v in firsts.items() if v}
        key = section_key(t)
        for a in client.get_all(f"courses/{t.course_id}/assignments"):
            week = week_of(a["name"], args.week)
            topic = a.get("discussion_topic")
            if not week or not topic:
                continue
            posts = topic_posts(client.get(
                f"courses/{t.course_id}/discussion_topics/{topic['id']}/view"), firsts)
            per: dict[int, list[tuple[int, dict]]] = defaultdict(list)
            for uid, eid, m in posts:
                if uid in studs:
                    per[uid].append((eid, m))
                    rows.append({"section": key, "week": week, "student": studs[uid]["name"],
                                 "entry": eid, **m})
            tally = Counter()
            for uid, s in studs.items():
                ents = per.get(uid, [])
                if not ents:
                    continue
                forced = s["sis"] in full
                plan.append({"course": t.course_id, "label": key, "assignment": a["id"],
                             "topic": topic["id"], "week": week, "user": uid,
                             "name": s["name"], "full_credit": forced,
                             "entries": [e for e, _ in ents]})
                tally[score_for(len(ents), forced)] += 1
                short = sum(1 for _, m in ents if m["words"] < SHORT_WORDS)
                copied = sum(1 for _, m in ents if m["max_overlap"] >= OVERLAP)
                ticked = any(e in kept for e, _ in ents)
                if forced or (len(ents) >= 2 and not short and not copied and not ticked):
                    continue
                why = ["denied in an earlier review" if ticked and len(ents) >= 2
                       and not short and not copied else "",
                       f"one post only ({PARTIAL} pt)" if len(ents) == 1 else "",
                       f"{short} post(s) under {SHORT_WORDS} words" if short else "",
                       f"{copied} post(s) sharing {OVERLAP:.0%}+ phrasing with another student"
                       if copied else ""]
                sg = (f"{client.base}/courses/{t.course_id}/gradebook/speed_grader"
                      f"?assignment_id={a['id']}&student_id={uid}")
                flagged[week].append(f"- **{key}**, {s['name']}: "
                               f"{'; '.join(x for x in why if x)}. [SpeedGrader]({sg})")
                for eid, m in ents:
                    box = "x" if eid in kept else " "
                    flagged[week].append(f"    - [{box}] deny entry `{eid}` ({describe(m)}): {client.base}"
                                   f"/courses/{t.course_id}/discussion_topics/{topic['id']}"
                                   f"?entry_id={eid}")
            line = (f"{len(per)} of {len(studs)} posted; "
                    f"{tally[FULL]} at {FULL}, {tally[PARTIAL]} at {PARTIAL}")
            print(f"{t.label} {week}: {line}")
            summary[week].append(f"- {key}: {line}")

    title = (f"Discussion grading: {', '.join(args.week)}" if args.week
             else f"Discussion grading {args.term or ''}".strip())
    body = [f"# {title}", "",
            f"Rule: 2+ credited posts = {FULL}, 1 = {PARTIAL}, 0 = 0. Every credited post "
            "gets a like; no comments are written.",
            "Everyone not listed has 2+ posts of normal length.", "",
            "Tick **deny** on any post that does not earn credit.", ""]
    for week in sorted(summary, key=_week_order):
        body += [f"## {week}", ""] + summary[week] + [""]
        body += (flagged[week] or ["Nobody needs review."]) + [""]
    if not summary:
        body.append("No discussion assignments matched.")
    text = "\n".join(body) + "\n"
    _private_write(wd / "plan.json", json.dumps(plan))
    _private_write(wd / "REVIEW.md", text)
    if rows:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
        _private_write(wd / "METRICS.csv", buf.getvalue())
    n = sum(1 for lines in flagged.values() for line in lines if line.startswith("- **"))
    print(f"\n{n} to review: {wd / 'REVIEW.md'}")

    if note:
        lost = kept - {e for p in plan for e in p["entries"]}
        if lost:
            print(f"warning: ticked entries no longer in Canvas (deleted posts?): {sorted(lost)}")
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        fm = ("---\n"
              f"title: \"{title}\"\n"
              "type: report\n"
              f"term: {args.term or ''}\n"
              "tags: [teaching, discussion, grading, internal]\n"
              "visibility: private\nicon: LiClipboardCheck\niconColor: var(--text-normal)\n"
              f"created: {stamp}\n---\n")
        how = ("> [!info] How to use this\n"
               "> Tick **deny** on a post that does not earn credit, then run "
               f"`reg-canvas discussions apply --workdir {args.workdir} --note '{note}' "
               "--week \"Week N\"` for that week's dry run. Rerun `review` any time: "
               "it adds new posts and keeps your ticks.\n")
        head, rest = text.split("\n", 1)
        _private_write(note, fm + head + "\n\n" + how + rest)
        print(f"Vault note: {note}" + (f" (kept {len(kept)} tick(s))" if kept else ""))
    return 0


def note_path(args) -> Path | None:
    if getattr(args, "note", None):
        return Path(args.note).expanduser()
    if getattr(args, "no_note", False) or not (args.vault_root and args.term):
        return None
    return default_note(Path(args.vault_root), args.term, args.week)


_TICK = re.compile(r"^\s*- \[[xX]\] deny entry `(\d+)`", re.M)


def _file_denials(wd: Path) -> set[int]:
    if not (wd / "deny.txt").exists():
        return set()
    return {int(t) for t in (wd / "deny.txt").read_text().split()}


def denials(wd: Path, note: Path | None) -> set[int]:
    deny = _file_denials(wd)
    if note and note.exists():
        deny |= {int(x) for x in _TICK.findall(note.read_text(encoding="utf-8"))}
    return deny


POST_GRADES = ("mutation($id: ID!){postAssignmentGrades(input:{assignmentId:$id})"
               "{progress{id} errors{message}}}")


def apply(client: CanvasClient, args) -> int:
    wd = Path(args.workdir).expanduser()
    try:
        plan = json.loads((wd / "plan.json").read_text())
    except FileNotFoundError:
        raise GradingError(f"no plan in {wd}; run reg-canvas discussions review first") from None
    if not args.week:
        weeks = sorted({p["week"] for p in plan}, key=_week_order)
        raise GradingError("name the week(s) to apply with --week, e.g. --week \"Week 7\"; "
                           f"this review covers {', '.join(weeks) or 'nothing'}. Applying "
                           "an older week overwrites the grades already entered for it.")
    note = Path(args.note).expanduser() if args.note else None
    deny = denials(wd, note)
    if deny:
        print(f"denying {len(deny)} post(s): {sorted(deny)}")

    groups: dict[tuple, list] = defaultdict(list)
    for p in plan:
        if args.week and not any(p["week"].startswith(w) for w in args.week):
            continue
        credited = [e for e in p["entries"] if e not in deny]
        groups[(p["course"], p["label"], p["assignment"], p["topic"], p["week"])].append(
            (p, credited, score_for(len(credited), p["full_credit"])))

    for (cid, label, aid, tid, week), rows in sorted(groups.items()):
        current = {s["user_id"]: s.get("score")
                   for s in client.get_all(f"courses/{cid}/assignments/{aid}/submissions")}
        grades = {str(p["user"]): {"posted_grade": str(s)}
                  for p, _, s in rows if current.get(p["user"]) != s}
        likes = [e for _, cr, _ in rows for e in cr]
        tally = Counter(s for _, _, s in rows)
        denied = [p["name"] for p, cr, _ in rows if len(cr) < len(p["entries"])]
        print(f"{label} {week}: set {len(grades)} grade(s) {dict(sorted(tally.items(), reverse=True))}, "
              f"like {len(likes)} post(s)"
              + (f", denied a post for {', '.join(denied)}" if denied else "")
              + (", then post the assignment's grades" if args.post else ""))
        if not args.apply:
            continue
        if grades:
            client.wait_progress(client.post(
                f"courses/{cid}/assignments/{aid}/submissions/update_grades",
                {"grade_data": grades}, idempotent=True))
        for e in likes:
            client.post(f"courses/{cid}/discussion_topics/{tid}/entries/{e}/rating", {"rating": 1},
                        idempotent=True)
        if args.post:
            r, _ = client.request("POST", f"{client.base}/api/graphql",
                                  data={"query": POST_GRADES, "variables": {"id": str(aid)}},
                                  idempotent=True)
            errs = (((r or {}).get("data") or {}).get("postAssignmentGrades") or {}).get("errors")
            if errs:
                raise GradingError(f"{label} {week}: posting failed: {errs}")
    print("dry run; add --apply to send" if not args.apply else "done")
    return 0


def cmd_discussions(client: CanvasClient, args, targets) -> int:
    if args.action == "review":
        return review(client, args, targets)
    return apply(client, args)

"""triage_report.py — two-tier (Part A/B/C) authenticity audit report.

Part A: Verified git facts (audit-grade, independently reproducible).
Part B: Advisory triage signal (heuristic; not proof, not a grade input).
Part C: Limitations and responsible use.

Deliverable forensics: for each declared deliverable, emit per-deliverable
VERIFIABLE git facts — presence at a grading commit, first-appearance commit,
and auto-zero trigger.  Every fact carries the exact reproduce command so a
third party can confirm it without trusting this tool.
"""
from __future__ import annotations

import datetime
import fnmatch
import re
import subprocess
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Glob → POSIX-ERE helper
# ---------------------------------------------------------------------------

def _glob_to_basename_ere(pattern: str) -> str:
    """Convert an fnmatch *pattern* to a POSIX-ERE that matches a path's BASENAME.

    Rules:
      - Escape ERE metacharacters in the pattern EXCEPT the glob wildcards ``*``
        and ``?``.
      - ``*``  → ``[^/]*``
      - ``?``  → ``[^/]``
      - Anchored so it matches only the basename: prefix ``(^|/)`` suffix ``$``.

    Examples::

        makefile  → (^|/)makefile$
        *.c       → (^|/)[^/]*\\.c$
        lab?.txt  → (^|/)lab[^/]\\.txt$
    """
    # ERE metacharacters to escape (all except * and ? which are glob wildcards)
    _ERE_META = r'\.+^${}[]|()'

    parts: list[str] = []
    for ch in pattern:
        if ch == '*':
            parts.append('[^/]*')
        elif ch == '?':
            parts.append('[^/]')
        elif ch in _ERE_META:
            parts.append('\\' + ch)
        else:
            parts.append(ch)

    return '(^|/)' + ''.join(parts) + '$'


# ---------------------------------------------------------------------------
# Git helper (local; mirrors triage_signals._git for self-containment)
# ---------------------------------------------------------------------------

def _git(repo: Path, *args) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        capture_output=True, text=True,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _ls_tree(repo: Path, ref: str) -> list[str]:
    """Return every path in the tree at *ref* (recursive, names only)."""
    out = _git(repo, "ls-tree", "-r", "--name-only", ref)
    if not out:
        return []
    return out.splitlines()


def _match_paths(paths: list[str], match_pattern: str) -> list[str]:
    """Return all paths whose BASENAME matches *match_pattern* case-insensitively."""
    pat = match_pattern.lower()
    return [p for p in paths if fnmatch.fnmatch(Path(p).name.lower(), pat)]


def _first_added(repo: Path, match_pattern: str) -> tuple[str | None, str | None]:
    """Return (short_sha, iso) of the commit where a matching file FIRST appeared.

    Strategy: walk ``git log --reverse --diff-filter=A --name-only`` and apply
    the same case-insensitive fnmatch rule on each path's basename.  This is
    the fallback-first approach the spec recommends for reliability across
    case differences and glob patterns.
    """
    out = _git(
        repo, "log", "--reverse", "--diff-filter=A",
        "--format=%x01%h\t%aI",   # sentinel line before sha+iso
        "--name-only",
    )
    if not out:
        return None, None

    current_sha: str | None = None
    current_iso: str | None = None
    pat = match_pattern.lower()

    for raw_line in out.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("\x01"):
            # sentinel + "sha\tiso"
            parts = line[1:].split("\t", 1)
            current_sha = parts[0] if parts else None
            current_iso = parts[1] if len(parts) > 1 else None
        else:
            # file path line
            if fnmatch.fnmatch(Path(line).name.lower(), pat):
                return current_sha, current_iso

    return None, None


# ---------------------------------------------------------------------------
# Release sanitizer
# ---------------------------------------------------------------------------

def sanitize_release(md: str) -> str:
    """Flatten Obsidian-isms for the release (Chair / registrar) variant.

    Transforms applied:
    - Wikilinks with alias: ``[[target|alias]]`` → ``alias``
    - Wikilinks without alias: ``[[target]]`` → last path segment of target
      (e.g. ``[[notes/foo]]`` → ``foo``)
    - Callout markers on blockquote lines:
      ``> [!type] rest`` → ``> rest``
      ``> [!type]`` (bare) → ``>`` (marker dropped, blank quote retained)

    Leaves em-dashes, § and other Unicode text glyphs untouched.
    """
    # Wikilinks: [[target|alias]] → alias; [[target]] → last segment of target
    def _wikilink(m: re.Match) -> str:
        inner = m.group(1)
        if "|" in inner:
            # [[target|alias]] — return alias
            return inner.split("|", 1)[1]
        else:
            # [[target]] — return last path segment
            return inner.rsplit("/", 1)[-1]

    md = re.sub(r"\[\[([^\[\]]+)\]\]", _wikilink, md)

    # Callout markers: "> [!type] rest" → "> rest"  /  "> [!type]" → ">"
    def _callout(m: re.Match) -> str:
        prefix = m.group(1)   # ">" + optional leading spaces
        rest = m.group(3)     # text after the marker (may be empty)
        if rest:
            return f"{prefix} {rest}"
        return prefix

    md = re.sub(r"^(>\s*)\[![^\]]+\](\s+(.+))?$", _callout, md, flags=re.MULTILINE)

    return md


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def deliverable_forensics(
    repo_path: Any,
    deliverables: list[dict],
    grading_ref: str = "HEAD",
) -> list[dict]:
    """For each deliverable dict, return a result dict with verifiable git facts.

    Deliverable dict keys:
        name        display name (required)
        match       fnmatch pattern matched against file basenames (required)
        required    bool, default False
        auto_zero   bool, default False
        min_count   int, default 1

    Result dict keys (all):
        name, match, required, auto_zero
        present_at_grading          bool
        matched_paths_at_grading    list[str]
        first_added_sha             str | None
        first_added_iso             str | None
        triggers_auto_zero          bool
        reproduce                   {"presence": str, "first_added": str}
    """
    repo = Path(repo_path)

    tree_at_grading = _ls_tree(repo, grading_ref)

    results = []
    for deliv in deliverables:
        name = deliv["name"]
        match = deliv["match"]
        required = bool(deliv.get("required", False))
        auto_zero = bool(deliv.get("auto_zero", False))
        min_count = int(deliv.get("min_count", 1))

        matched = _match_paths(tree_at_grading, match)
        present = len(matched) >= min_count

        sha, iso = _first_added(repo, match)

        triggers = auto_zero and not present

        # Reproduce commands — literal strings a third party can run.
        # Use "cd <repo> && git ..." so the git subcommands read as plain
        # "git ls-tree ..." / "git log ..." — copy-paste friendly.
        # Convert the fnmatch pattern to a POSIX-ERE so that glob patterns
        # like *.c produce a correct grep -iE expression instead of treating
        # * as a regex quantifier.
        ere = _glob_to_basename_ere(match)
        presence_cmd = (
            f"cd <repo> && git ls-tree -r --name-only {grading_ref}"
            f" | grep -iE '{ere}'"
        )
        first_added_cmd = (
            f"cd <repo> && git log --reverse --diff-filter=A"
            f" --format='%h%x09%aI' --name-only | grep -iE '{ere}'"
        )

        results.append({
            "name": name,
            "match": match,
            "required": required,
            "auto_zero": auto_zero,
            "present_at_grading": present,
            "matched_paths_at_grading": matched,
            "first_added_sha": sha,
            "first_added_iso": iso,
            "triggers_auto_zero": triggers,
            "reproduce": {
                "presence": presence_cmd,
                "first_added": first_added_cmd,
            },
        })

    return results


# ---------------------------------------------------------------------------
# render_report — two-tier (Part A/B/C) authenticity audit report assembler
# ---------------------------------------------------------------------------

def _ledger_table(ledger: list) -> str:
    """Render the commit ledger as a fixed-width fenced block.

    Columns: sha  iso  author  subject.  Bot rows are tagged [bot].
    """
    lines = []
    for e in ledger:
        tag = "[bot]      " if e.is_bot else "           "
        # Trim iso to 'YYYY-MM-DD HH:MM' for layout (16 chars)
        iso_short = e.iso[:16] if len(e.iso) >= 16 else e.iso
        lines.append(f"{e.sha:<10} {iso_short}  {tag}{e.author:<20}  {e.subject}")
    return "```\n" + "\n".join(lines) + "\n```"


def _part_a(student: dict, cfg: dict, facts, forensics: list[dict],
            *, release: bool, grading_ref: str | None = None) -> str:
    """Render Part A — Verified record (audit-grade)."""
    asgn = cfg.get("assignment", {})
    repo_name = (
        asgn.get("repo_prefix", "") + student["github_username"]
    )
    org = asgn.get("org", "")
    course = asgn.get("course", "")
    section = asgn.get("section", "")
    asgn_name = asgn.get("name", "")
    profile = cfg.get("profile", "")
    engine_sha = cfg.get("engine_sha", "")
    schema_version = cfg.get("schema_version", "")
    today = datetime.date.today().isoformat()

    # HEAD SHA — last ledger entry (most recent commit)
    head_sha = facts.ledger[-1].sha if facts.ledger else "(unknown)"

    # Build SSID line — omit when release=True
    ssid_line = ""
    if not release:
        ssid_line = f"| Student ID (SSID) | `{student['student_id']}` |\n"

    # Build grading commit row — only when a grading ref is provided
    grading_ref_line = ""
    if grading_ref is not None:
        # Shorten to 7 chars if it looks like a full SHA (40 hex chars)
        short = grading_ref[:7] if (len(grading_ref) == 40 and all(c in "0123456789abcdef" for c in grading_ref)) else grading_ref
        grading_ref_line = f"| Grading commit (deliverables) | `{short}` |\n"

    # --- A.1 Provenance ---
    a1 = f"""\
## A.1 Provenance (pins exactly what was examined)

| Field | Value |
|---|---|
| Repository | `{repo_name}` (org `{org}`) |
| Repo HEAD examined | `{head_sha}` |
{grading_ref_line}| Examined by | Anthony Giacalone, {today} |
| Tooling (Part B only) | `assignment-triage` @ `{engine_sha}`; engine `grader.py` |
| Profile | {profile} (signal weights declared in A.5) |
| Course / Section | {course} §{section} — {asgn_name} |
| Student | {student['display_name']} (`{student['github_username']}`) |
{ssid_line}"""

    # --- A.2 Commit ledger ---
    a2 = f"""\
## A.2 Commit ledger (verbatim `git log`)

Author `{student['github_username']}`. `[bot]` rows are GitHub Classroom scaffolding \
(excluded from the Part B screen). Times ISO-8601 author date. Messages trimmed to one \
line for layout.

{_ledger_table(facts.ledger)}"""

    # --- A.3 Deliverable facts ---
    deliverable_blocks = []
    for d in forensics:
        present_str = "**Yes**" if d["present_at_grading"] else "**No** — ABSENT at grading ref"
        auto_zero_str = "**Triggers automatic zero**" if d["triggers_auto_zero"] else "Does not trigger"
        first_sha = d["first_added_sha"] or "(never added)"
        first_iso = d["first_added_iso"] or ""
        matched = ", ".join(f"`{p}`" for p in d["matched_paths_at_grading"]) or "(none)"
        block = f"""\
**Deliverable: {d['name']}** (match pattern: `{d['match']}`, required: {d['required']}, auto-zero: {d['auto_zero']})

- Present at grading ref: {present_str}
- Matched paths: {matched}
- First added commit: `{first_sha}` {first_iso}
- Auto-zero status: {auto_zero_str}"""
        deliverable_blocks.append(block)

    a3 = "## A.3 Published requirement and deliverable facts\n\n" + "\n\n".join(deliverable_blocks)

    # --- A.4 Reproduce commands ---
    reproduce_blocks = []
    for d in forensics:
        block = f"""\
### {d['name']}

```
# Presence at grading ref:
{d['reproduce']['presence']}

# First added commit:
{d['reproduce']['first_added']}
```"""
        reproduce_blocks.append(block)

    a4 = "## A.4 Reproduce Part A\n\n" + "\n\n".join(reproduce_blocks)

    # --- A.5 Screen configuration ---
    thresholds = cfg.get("thresholds", {})
    weights = cfg.get("weights", {})
    _thresh_op = {"pass": ">=", "flag": "<="}
    thresh_str = ", ".join(
        f"score {_thresh_op.get(k, '>=')} {v}" for k, v in thresholds.items()
    )
    weights_str = ", ".join(f"{k} {v}" for k, v in weights.items()) or "(defaults)"
    a5 = f"""\
## A.5 Screen configuration (for reproducibility of Part B)

Thresholds: {thresh_str}. Weights: {weights_str}. \
Schema version: {schema_version}. Engine SHA: `{engine_sha}`."""

    header = """\
# Part A — Verified record (audit-grade, independently reproducible)

Every fact below is derivable by a third party with repository access by running the
commands in A.4 against the pinned commit. No interpretation is required to confirm them.
"""

    return "\n\n".join([header, a1, a2, a3, a4, a5])


def _part_b(student: dict, cfg: dict, score: tuple) -> str:
    """Render Part B — Advisory triage signal (heuristic; not proof)."""
    points, reasoning, bucket = score
    thresholds = cfg.get("thresholds", {})
    pass_thresh = thresholds.get("pass", 60)
    flag_thresh = thresholds.get("flag", 20)

    bucket_desc = {
        "PASS": f"clear pass (score {points} >= {pass_thresh})",
        "REVIEW": f"review bucket ({flag_thresh} < score {points} < {pass_thresh})",
        "FLAG": f"flag bucket (score {points} <= {flag_thresh})",
    }.get(bucket, f"bucket {bucket} (score {points})")

    return f"""\
# Part B — Advisory triage signal (heuristic; not proof, not a grade input)

`assignment-triage` is a screening heuristic. By its own design it is "100% triage — a \
flag is a prompt to look, not a verdict — no student is penalized without human review." \
It awards points for behavioral signals that are characteristic of (but not unique to) \
genuine human development. The thresholds and weights are hand-set starting points, not \
statistically calibrated, and the tool publishes no error rate. A score is therefore \
advisory only and is **not proof** of anything on its own. It is sound to use it to \
corroborate that there is no integrity concern; it would not be sound to treat any score \
as proof or to base an adverse finding on it without independent human review.

Running the screen across the repository's commit history produced the following result for \
**{student['display_name']}** (`{student['github_username']}`):

- **Score:** {points}
- **Bucket:** {bucket_desc}
- **Reasoning:** {reasoning}

These are advisory signals only. See Part C for limitations."""


def _part_c(cfg: dict) -> str:
    """Render Part C — Limitations and responsible use."""
    schema_version = cfg.get("schema_version", "")
    signal_set_version = cfg.get("signal_set_version", 1)
    engine_sha = cfg.get("engine_sha", "")
    today = datetime.date.today().isoformat()

    return f"""\
# Part C — Limitations and responsible use

- **Heuristic, not validated.** Weights and thresholds are hand-calibrated starting \
points with no published false-positive / false-negative rate. The score is a \
prioritization aid, never proof.
- **Triage, not verdict.** Used here only to clear a concern (the safe error direction). \
It must never be the sole basis for an adverse academic-integrity finding; that requires \
independent human review.
- **Two commit views, one report.** The advisory screen (Part B) considers the full \
commit history, including any commits after the deadline; the verified record (Part A) \
pins deliverable facts to the grading commit. Post-deadline commits can only raise an \
advisory score, never lower it.
- **Commit timestamps are self-reported.** Git author and committer dates are set \
client-side and are, in principle, forgeable. For contested timelines, GitHub server-side \
push/event timestamps are the stronger source and are the recommended hardening step.
- **Instructor context is not modeled.** The tool has no knowledge of a student's prior \
work or caliber; the instructor supplies that judgment.
- **Versioning.** Report schema v{schema_version}; signal set v{signal_set_version}; advisory signal set per the pinned \
engine SHA `{engine_sha}`. Future signal sets append; each report pins the engine and \
configuration so results remain reproducible and interpretable as the methodology evolves.

*Prepared by Anthony Giacalone (instructor) on {today}. Part A is independently \
verifiable from the repository; Part B is advisory and bounded as described in Part C.*"""


def render_report(
    student: dict,
    cfg: dict,
    facts: Any,
    forensics: list[dict],
    score: tuple,
    release: bool = False,
    grading_ref: str | None = None,
) -> str:
    """Assemble the two-tier (Part A/B/C) authenticity audit report.

    Parameters
    ----------
    student:
        ``{display_name, student_id, github_username}``
    cfg:
        Assignment manifest cfg dict (assignment sub-dict, profile, thresholds,
        weights, schema_version, engine_sha).
    facts:
        ``RepoFacts`` instance (uses ``facts.ledger``).
    forensics:
        List of dicts from ``deliverable_forensics``.
    score:
        Tuple ``(points: int, reasoning: str, bucket: str)``.
    release:
        When ``True``, the student_id (SSID) is omitted from the output.
        (Full sanitization — wikilink stripping, callout flattening, etc. — is
        a later task; for now ``release=True`` only guarantees the SSID does
        not appear.)
    grading_ref:
        When provided, a ``| Grading commit (deliverables) | `<ref>` |`` row
        is added to A.1 so readers know which commit the deliverable facts pin
        to (distinct from Repo HEAD). Optional; row is omitted when ``None``.

    Returns
    -------
    str
        Markdown document.
    """
    asgn = cfg.get("assignment", {})
    course = asgn.get("course", "")
    section = asgn.get("section", "")
    asgn_name = asgn.get("name", "")
    today = datetime.date.today().isoformat()

    # YAML front-matter
    frontmatter = f"""\
---
title: "Authenticity Review — {course} §{section}, {asgn_name}"
subtitle: "Student: {student['display_name']}"
author: "Anthony Giacalone · Lecturer, Computer Engineering & Computer Science, CSULB"
date: "{today}"
---"""

    # Preamble — How to read this document
    preamble = """\
**How to read this document.** It is in two tiers, and they do not carry equal
weight:

> **Part A — Verified record (audit-grade).** Immutable git facts, pinned by commit
> hash and independently reproducible. These are facts, not inferences.
>
> **Part B — Advisory triage signal (heuristic; not proof).** A screening score that
> prioritizes work for human review. It is not evidence of anything on its own and is
> not the basis for any grade or finding.

**Bottom line.** The verified record (Part A) contains the git facts that withstand
audit. The advisory screen (Part B) is a heuristic signal bounded by the limitations
in Part C. Nothing in Part B is used adversely against the student without independent
human review."""

    part_a = _part_a(student, cfg, facts, forensics, release=release, grading_ref=grading_ref)
    part_b = _part_b(student, cfg, score)
    part_c = _part_c(cfg)

    sections = [frontmatter, preamble, "---", part_a, "---", part_b, "---", part_c]
    md = "\n\n".join(sections)

    # Enforce SSID omission and Obsidian-ism sanitization for release variant
    if release:
        md = md.replace(student["student_id"], "[REDACTED]")
        md = sanitize_release(md)

    return md


# ---------------------------------------------------------------------------
# to_pdf — render a report .md to PDF via pandoc/xelatex (the release-report invocation)
# ---------------------------------------------------------------------------

def to_pdf(md_path, pdf_path):
    """Render a report .md to PDF via pandoc/xelatex (the release-report invocation).

    Matches the exact flags used when producing the hand-authored release PDF.
    Raises RuntimeError if pandoc is not installed.
    """
    import shutil
    if not shutil.which("pandoc"):
        raise RuntimeError("pandoc not found; install pandoc + a LaTeX engine (xelatex)")
    subprocess.run(
        ["pandoc", str(md_path), "-o", str(pdf_path),
         "--pdf-engine=xelatex", "-V", "geometry:margin=1in",
         "-V", "fontsize=11pt", "-V", "colorlinks=true", "-V", "linkcolor=black"],
        check=True)
    return pdf_path

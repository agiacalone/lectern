"""Guard-file integrity — Part A facts about instructor-authored files.

A lab template ships files the student is not asked to edit: ``AGENTS.md``
(the high-authority AI-assistant surface), the honor statement, the autograde
workflow. Editing or deleting one is a **visible, deliberate act in the git
history**, and this module turns it into an audit-grade fact: what the file
looked like when it was distributed, what it looks like at the grading commit,
and which commits changed it.

==This is a fact, never a score.== It deliberately does not register as a
triage signal and does not move any bucket. A student may have an innocuous
reason to touch ``AGENTS.md`` (adding their name, resolving a merge), and the
engine's standing rule is that no adverse finding is made without human review.
The output is a prompt to look, with the reproduce command attached.
"""
from __future__ import annotations

import fnmatch
import hashlib
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# The files a lab template ships and the student is not asked to edit.
DEFAULT_GUARD_FILES: list[str] = ["AGENTS.md"]

# Status vocabulary, ordered most-interesting first for reporting.
STATUS_DELETED = "deleted"
STATUS_MODIFIED = "modified"
STATUS_INTACT = "intact"
STATUS_ABSENT = "absent"

_STATUS_ORDER = {
    STATUS_DELETED: 0,
    STATUS_MODIFIED: 1,
    STATUS_INTACT: 2,
    STATUS_ABSENT: 3,
}

#: Statuses that warrant a human look. ``absent`` does not: it usually means the
#: template shipped no such file, which is a fact about the lab, not the student.
NOTABLE = (STATUS_DELETED, STATUS_MODIFIED)


def _git(repo: Path, *args) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        capture_output=True, text=True,
    )
    return result.stdout.strip()


def _git_bytes(repo: Path, *args) -> bytes | None:
    result = subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _is_bot(author: str) -> bool:
    """True when the commit author is GitHub scaffolding, not the student."""
    return "[bot]" in author


@dataclass
class GuardTouch:
    """One commit that added, modified, deleted or renamed a guard file."""
    sha: str
    iso: str
    author: str
    subject: str
    change: str          # A / M / D / R… (git --name-status letter)
    is_bot: bool


@dataclass
class GuardFileFact:
    """Verified record for one guard-file pattern in one repo."""
    pattern: str
    path: str | None                     # resolved repo path, if it ever existed
    status: str                          # intact | modified | deleted | absent
    present_at_grading: bool
    baseline_source: str                 # "template-sha256" | "first-commit" | "none"
    baseline_sha: str | None             # commit that first added it
    baseline_iso: str | None
    content_sha256: str | None           # content at the grading ref
    touches: list[GuardTouch] = field(default_factory=list)
    student_touches: int = 0             # non-bot commits after the file first appeared
    reproduce: dict = field(default_factory=dict)

    @property
    def notable(self) -> bool:
        """True when a human should look at this repo's guard file."""
        return self.status in NOTABLE

    def summary(self) -> str:
        """One-cell summary for a CSV column or a table."""
        if self.status in (STATUS_INTACT, STATUS_ABSENT):
            return self.status
        return f"{self.status}({self.student_touches})" if self.student_touches else self.status


def _paths_ever(repo: Path, pattern: str) -> list[str]:
    """Every path in the repo's history whose BASENAME matches *pattern*.

    History-wide, not tree-at-ref: a deleted guard file is exactly the case that
    matters, and it is not in the grading tree.
    """
    out = _git(repo, "log", "--pretty=format:", "--name-only", "--diff-filter=AMRD")
    pat = pattern.lower()
    seen: dict[str, None] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if fnmatch.fnmatch(Path(line).name.lower(), pat):
            seen.setdefault(line, None)
    return list(seen)


def _touches(repo: Path, path: str) -> list[GuardTouch]:
    """Every commit touching *path*, oldest first, with its change letter."""
    out = _git(
        repo, "log", "--reverse", "--format=%x01%h\t%aI\t%an\t%s",
        "--name-status", "--", path,
    )
    if not out:
        return []
    touches: list[GuardTouch] = []
    sha = iso = author = subject = ""
    for raw in out.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("\x01"):
            parts = line[1:].split("\t", 3)
            sha = parts[0] if len(parts) > 0 else ""
            iso = parts[1] if len(parts) > 1 else ""
            author = parts[2] if len(parts) > 2 else ""
            subject = parts[3] if len(parts) > 3 else ""
            continue
        change = line.split("\t", 1)[0].strip()
        if not change:
            continue
        touches.append(GuardTouch(
            sha=sha, iso=iso, author=author, subject=subject,
            change=change, is_bot=_is_bot(author),
        ))
    return touches


def _blob_sha256(repo: Path, ref: str, path: str) -> str | None:
    """SHA-256 of the file content at *ref*, or None when it is not there."""
    data = _git_bytes(repo, "show", f"{ref}:{path}")
    if data is None:
        return None
    return hashlib.sha256(data).hexdigest()


def guardfile_forensics(
    repo_path: Any,
    guard_files: list | None = None,
    grading_ref: str = "HEAD",
) -> list[GuardFileFact]:
    """Return one :class:`GuardFileFact` per declared guard file.

    Parameters
    ----------
    repo_path:
        Root of the student's clone.
    guard_files:
        Each entry is either a bare pattern (``"AGENTS.md"``) or a dict
        ``{"path": <fnmatch pattern>, "sha256": <hex digest of the distributed
        file>}``. ==Supply the ``sha256`` when you have it== — it compares
        against the template as *distributed*, so a student who edited the file
        inside a squashed initial import is still visible. Without it the
        baseline is the file's first appearance in this repo, which a squash can
        hide. Defaults to :data:`DEFAULT_GUARD_FILES`.
    grading_ref:
        The commit the deliverables are pinned to.
    """
    repo = Path(repo_path)
    specs = guard_files if guard_files is not None else DEFAULT_GUARD_FILES

    facts: list[GuardFileFact] = []
    for spec in specs:
        if isinstance(spec, dict):
            pattern = spec.get("path") or spec.get("match") or ""
            expected = (spec.get("sha256") or "").strip().lower() or None
        else:
            pattern, expected = str(spec), None
        if not pattern:
            continue

        matched = _paths_ever(repo, pattern)
        if not matched:
            facts.append(GuardFileFact(
                pattern=pattern, path=None, status=STATUS_ABSENT,
                present_at_grading=False, baseline_source="none",
                baseline_sha=None, baseline_iso=None, content_sha256=None,
                reproduce=_reproduce(pattern, None, grading_ref),
            ))
            continue

        # One pattern can legitimately match several paths (a nested AGENTS.md).
        # Report the most interesting one; ties resolve to the first found.
        candidates = [
            _one_path(repo, pattern, path, expected, grading_ref)
            for path in matched
        ]
        candidates.sort(key=lambda f: _STATUS_ORDER.get(f.status, 9))
        facts.append(candidates[0])

    return facts


def _one_path(repo: Path, pattern: str, path: str,
              expected: str | None, grading_ref: str) -> GuardFileFact:
    touches = _touches(repo, path)
    added = next((t for t in touches if t.change.startswith("A")), None)
    baseline_sha = added.sha if added else (touches[0].sha if touches else None)
    baseline_iso = added.iso if added else (touches[0].iso if touches else None)

    current = _blob_sha256(repo, grading_ref, path)
    present = current is not None

    if expected:
        baseline_source = "template-sha256"
        baseline_digest: str | None = expected
    elif baseline_sha:
        baseline_source = "first-commit"
        baseline_digest = _blob_sha256(repo, baseline_sha, path)
    else:
        baseline_source = "none"
        baseline_digest = None

    if not present:
        status = STATUS_DELETED
    elif baseline_digest is None:
        # Nothing to compare against; presence is all we can verify.
        status = STATUS_INTACT
    elif current == baseline_digest:
        status = STATUS_INTACT
    else:
        status = STATUS_MODIFIED

    # Student touches: non-bot commits, excluding the import that first added it.
    student_touches = sum(
        1 for t in touches
        if not t.is_bot and not (added is not None and t.sha == added.sha)
    )

    return GuardFileFact(
        pattern=pattern, path=path, status=status, present_at_grading=present,
        baseline_source=baseline_source, baseline_sha=baseline_sha,
        baseline_iso=baseline_iso, content_sha256=current, touches=touches,
        student_touches=student_touches,
        reproduce=_reproduce(pattern, path, grading_ref),
    )


def _reproduce(pattern: str, path: str | None, grading_ref: str) -> dict:
    """Literal commands a third party can run to confirm the facts."""
    target = path or pattern
    return {
        "history": (
            f"cd <repo> && git log --reverse --format='%h%x09%aI%x09%an%x09%s'"
            f" --name-status -- {target}"
        ),
        "content": f"cd <repo> && git show {grading_ref}:{target} | sha256sum",
        "diff": (
            f"cd <repo> && git diff <first-commit> {grading_ref} -- {target}"
        ),
    }


def cohort_summary(facts_by_repo: dict[str, list[GuardFileFact]]) -> dict:
    """Aggregate counts for a cohort-level line in a sweep report."""
    counts = {STATUS_INTACT: 0, STATUS_MODIFIED: 0,
              STATUS_DELETED: 0, STATUS_ABSENT: 0}
    notable: list[str] = []
    for repo, facts in facts_by_repo.items():
        worst = worst_status(facts)
        counts[worst] = counts.get(worst, 0) + 1
        if worst in NOTABLE:
            notable.append(repo)
    return {"counts": counts, "notable": sorted(notable), "n": len(facts_by_repo)}


def worst_status(facts: list[GuardFileFact]) -> str:
    """The most interesting status across *facts* (deleted > modified > intact > absent)."""
    return min(
        (f.status for f in facts),
        key=lambda st: _STATUS_ORDER.get(st, 9),
        default=STATUS_ABSENT,
    )


def fact_to_dict(f: GuardFileFact) -> dict:
    d = asdict(f)
    d["notable"] = f.notable
    d["summary"] = f.summary()
    return d

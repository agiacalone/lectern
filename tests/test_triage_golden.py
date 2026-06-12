"""test_triage_golden.py — synthetic FLAG/PASS regression: scoring + golden-file lock.

SYNTHETIC FIXTURES ONLY. The two repos built here are fabricated, deterministic
demos of a machine-generated-looking submission (FLAG) and a human-looking
submission (PASS). They use fictional Gotham characters and an impossible
section (CECS 326 §99). No real student appears anywhere in this file.

Jobs:
  1. `to_pdf` smoke-test: pandoc produces a real (>1 KB) PDF.
  2. Verdict regression: the FLAG repo scores FLAG/REVIEW and the PASS repo
     scores PASS under the shipped `triage_profiles.yaml` short-project profile.
  3. Golden-file regression: each generator's release output is locked against
     regressions (volatile SHAs / dates masked).
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FIXT = Path(__file__).parent / "fixtures" / "triage"

# Banner prepended to every generated synthetic report, immediately under the
# YAML frontmatter, so no reader can mistake a demo artifact for a real review.
SYNTHETIC_BANNER = (
    "> **Synthetic example — fictional students, fabricated repositories; "
    "not a real authenticity review.**"
)


# ---------------------------------------------------------------------------
# Low-level deterministic repo builder
# ---------------------------------------------------------------------------

def _init_repo(repo: Path, author: str, email: str):
    repo.mkdir()
    base_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": author,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "commit.gpgsign",
        "GIT_CONFIG_VALUE_0": "false",
    }
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True, env=base_env)

    def _commit(dt, files, message, *, deletes=()):
        for fn in deletes:
            p = repo / fn
            if p.exists():
                p.unlink()
        for fn, content in files.items():
            p = repo / fn
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        env = {**base_env, "GIT_AUTHOR_DATE": dt, "GIT_COMMITTER_DATE": dt}
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo, check=True, env=env)

    return _commit


# ---------------------------------------------------------------------------
# FLAG case — Harley Quinn (machine-generated-looking repo)
# ---------------------------------------------------------------------------

def _build_harley_repo(tmp_path):
    """Build a deterministic fixture repo that LOOKS machine-generated → FLAG.

    Signature of a bulk dump:
      - The entire deliverable lands in a single commit (100% of insertions in
        one commit → fails the no_dump signal).
      - One day of activity (fails spread_days).
      - Generic commit message ("add solution"); no iterative development, no
        deletions, no cross-session churn.

    Returns (repo_path, grading_ref).
    """
    repo = tmp_path / "cecs-326-sp26-99-lab-02-semaphores-harley-quinn"
    commit = _init_repo(repo, "harley-quinn", "harley-quinn@users.noreply.github.com")

    # One bulk commit containing the whole deliverable, at a machine-even time.
    commit(
        "2026-05-16T03:00:00",
        {
            "main.c": (
                "#include <stdio.h>\n#include <semaphore.h>\n"
                "int main(){return 0;}\n"
            ),
            "barbarian.c": "// barbarian thread\nvoid barbarian(){sem_wait(NULL);}\n",
            "wizard.c": "// wizard thread\nvoid wizard(){sem_post(NULL);}\n",
            "rogue.c": "// rogue thread\nvoid rogue(){sem_wait(NULL);}\n",
            "Makefile": (
                "all: barbarian wizard rogue\n"
                "\tgcc -o lab2 main.c barbarian.c wizard.c rogue.c -lpthread\n"
            ),
        },
        "add solution",
    )

    grading_ref = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    return repo, grading_ref


def _harley_report(tmp_path, release=True):
    from lectern.triage_signals import RepoFacts
    from lectern.triage_engine import score_repo
    from lectern.triage_report import deliverable_forensics, render_report

    repo, grading_ref = _build_harley_repo(tmp_path)
    facts = RepoFacts.from_repo(repo)
    forensics = deliverable_forensics(
        repo,
        [{"name": "makefile", "match": "makefile", "required": True, "auto_zero": True}],
        grading_ref=grading_ref,
    )
    cfg = {
        "assignment": {
            "name": "Lab 02 — Semaphores",
            "course": "CECS 326",
            "section": "99",
            "org": "Giacalone-CECS",
            "repo_prefix": "cecs-326-sp26-99-lab-02-semaphores-",
        },
        "profile": "short-project",
        "thresholds": {"pass": 60, "flag": 20},
        "weights": {},
        "schema_version": 1,
        "engine_sha": "PINNED",
    }
    student = {
        "display_name": "Harley Quinn",
        "student_id": "000000001",
        "github_username": "harley-quinn",
    }
    score = score_repo(repo, cfg, profile="short-project")
    md = render_report(student, cfg, facts, forensics, score, release=release,
                       grading_ref=grading_ref)
    return _inject_banner(md)


# ---------------------------------------------------------------------------
# PASS case — Barbara Gordon (human-looking repo)
# ---------------------------------------------------------------------------

def _build_barbara_repo(tmp_path):
    """Build a deterministic fixture repo that LOOKS human-authored → PASS.

    Signature of genuine incremental development:
      - 8 commits across ~10 days at human-irregular times.
      - The deliverable grows over commits (files added/revised across sessions).
      - At least one revert/fix commit that DELETES lines (deletions signal).
      - No single-commit dump (no_dump passes).

    Returns (repo_path, grading_ref) where grading_ref pins the last commit
    before the due date (the Makefile is present well before then).
    """
    repo = tmp_path / "cecs-326-sp26-99-lab-02-semaphores-barbara-gordon"
    commit = _init_repo(repo, "barbara-gordon", "barbara-gordon@users.noreply.github.com")

    commit(
        "2026-05-06T19:42:00",
        {"main.c": "#include <stdio.h>\nint main(){return 0;}\n"},
        "initial skeleton",
    )
    commit(
        "2026-05-07T22:13:00",
        {
            "main.c": "#include <stdio.h>\n#include <semaphore.h>\nint main(){return 0;}\n",
            "barbarian.c": "// barbarian thread\nvoid barbarian(){}\n",
        },
        "stub out barbarian thread",
    )
    commit(
        "2026-05-09T16:05:00",
        {
            "wizard.c": "// wizard thread\nvoid wizard(){}\n",
            "rogue.c": "// rogue thread\nvoid rogue(){}\n",
        },
        "add wizard and rogue stubs",
    )
    commit(
        "2026-05-10T23:51:00",
        {
            "barbarian.c": (
                "// barbarian thread\n"
                "void barbarian(){\n  sem_wait(&mutex);\n  // critical section\n"
                "  sem_post(&mutex);\n}\n"
            ),
            "wizard.c": (
                "// wizard thread\n"
                "void wizard(){\n  sem_wait(&mutex);\n  sem_post(&mutex);\n}\n"
            ),
        },
        "implement semaphore waits in barbarian and wizard",
    )
    # Fix/revert commit: back out a buggy deadlock attempt (deletes lines).
    commit(
        "2026-05-12T11:27:00",
        {
            "barbarian.c": (
                "// barbarian thread\n"
                "void barbarian(){\n  sem_wait(&mutex);\n  sem_post(&mutex);\n}\n"
            ),
        },
        "fix deadlock: revert nested-lock attempt in barbarian",
    )
    commit(
        "2026-05-13T20:08:00",
        {
            "rogue.c": (
                "// rogue thread\n"
                "void rogue(){\n  sem_wait(&mutex);\n  sem_post(&mutex);\n}\n"
            ),
            "Makefile": (
                "all: barbarian wizard rogue\n"
                "\tgcc -o lab2 main.c barbarian.c wizard.c rogue.c -lpthread\n"
            ),
        },
        "wire up rogue and add Makefile",
    )
    commit(
        "2026-05-14T18:33:00",
        {
            "main.c": (
                "#include <stdio.h>\n#include <semaphore.h>\n"
                "sem_t mutex;\nint main(){sem_init(&mutex,0,1);return 0;}\n"
            ),
        },
        "debug: initialize mutex semaphore in main",
    )

    grading_ref = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    # A small post-grading polish commit (human projects keep moving).
    commit(
        "2026-05-15T21:19:00",
        {"README.md": "# Lab 02 — Semaphores\n\nBuild with `make`.\n"},
        "add README with build instructions",
    )

    return repo, grading_ref


def _barbara_report(tmp_path, release=True):
    from lectern.triage_signals import RepoFacts
    from lectern.triage_engine import score_repo
    from lectern.triage_report import deliverable_forensics, render_report

    repo, grading_ref = _build_barbara_repo(tmp_path)
    facts = RepoFacts.from_repo(repo)
    forensics = deliverable_forensics(
        repo,
        [{"name": "makefile", "match": "makefile", "required": True, "auto_zero": True}],
        grading_ref=grading_ref,
    )
    cfg = {
        "assignment": {
            "name": "Lab 02 — Semaphores",
            "course": "CECS 326",
            "section": "99",
            "org": "Giacalone-CECS",
            "repo_prefix": "cecs-326-sp26-99-lab-02-semaphores-",
            "assigned_date": "2026-05-05",
            "due_date": "2026-05-15",
        },
        "profile": "short-project",
        "thresholds": {"pass": 60, "flag": 20},
        "weights": {},
        "schema_version": 1,
        "engine_sha": "PINNED",
    }
    student = {
        "display_name": "Barbara Gordon",
        "student_id": "000000002",
        "github_username": "barbara-gordon",
    }
    score = score_repo(repo, cfg, profile="short-project")
    md = render_report(student, cfg, facts, forensics, score, release=release,
                       grading_ref=grading_ref)
    return _inject_banner(md)


# ---------------------------------------------------------------------------
# Banner injection — every synthetic report opens with the disclaimer
# ---------------------------------------------------------------------------

def _inject_banner(md: str) -> str:
    """Insert the synthetic-example banner immediately under the YAML frontmatter."""
    if SYNTHETIC_BANNER in md:
        return md
    lines = md.splitlines()
    # Frontmatter is delimited by the first two '---' lines.
    if lines and lines[0].strip() == "---":
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end = i
                break
        if end is not None:
            new = lines[: end + 1] + ["", SYNTHETIC_BANNER] + lines[end + 1:]
            return "\n".join(new)
    # No frontmatter found — prepend the banner.
    return SYNTHETIC_BANNER + "\n\n" + md


# ---------------------------------------------------------------------------
# Golden normalizer — mask volatile fields so the golden is stable
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    """Mask volatile content and collapse trailing whitespace for stable golden compare."""
    s = re.sub(r'`[0-9a-f]{7,40}`', '`SHA`', s)
    s = re.sub(r'\b[0-9a-f]{7,40}\b', 'SHA', s)
    today_pat = re.compile(r'\d{4}-\d{2}-\d{2}')
    s = today_pat.sub('DATE', s)
    return "\n".join(line.rstrip() for line in s.strip().splitlines())


# ---------------------------------------------------------------------------
# Tests — verdicts
# ---------------------------------------------------------------------------

def test_harley_flags(tmp_path):
    """The machine-generated-looking repo must NOT pass: FLAG or REVIEW."""
    from lectern.triage_engine import score_repo
    repo, _ = _build_harley_repo(tmp_path)
    cfg = {"assignment": {"name": "Lab 02 — Semaphores", "course": "CECS 326",
                          "section": "99"},
           "profile": "short-project", "thresholds": {"pass": 60, "flag": 20},
           "weights": {}}
    points, _reasoning, bucket = score_repo(repo, cfg, profile="short-project")
    assert bucket in {"FLAG", "REVIEW"}, f"expected FLAG/REVIEW, got {bucket} (score {points})"


def test_barbara_passes(tmp_path):
    """The human-looking repo must PASS under the shipped short-project profile."""
    from lectern.triage_engine import score_repo
    repo, _ = _build_barbara_repo(tmp_path)
    cfg = {"assignment": {"name": "Lab 02 — Semaphores", "course": "CECS 326",
                          "section": "99",
                          "assigned_date": "2026-05-05", "due_date": "2026-05-15"},
           "profile": "short-project", "thresholds": {"pass": 60, "flag": 20},
           "weights": {}}
    points, _reasoning, bucket = score_repo(repo, cfg, profile="short-project")
    assert bucket == "PASS", f"expected PASS, got {bucket} (score {points})"


# ---------------------------------------------------------------------------
# Tests — report content
# ---------------------------------------------------------------------------

def test_synthetic_reports_carry_banner(tmp_path):
    """Every generated synthetic report opens with the fictional-example banner."""
    h = tmp_path / "h"; h.mkdir()
    b = tmp_path / "b"; b.mkdir()
    harley = _harley_report(h, release=True)
    barbara = _barbara_report(b, release=True)
    for md in (harley, barbara):
        assert SYNTHETIC_BANNER in md
        # Banner sits under the frontmatter (after the closing '---', before Part A).
        assert md.index(SYNTHETIC_BANNER) < md.index("Part A")


def test_harley_report_states_the_load_bearing_facts(tmp_path):
    """Part A/B/C structure + the bulk-dump signal surfaces in the advisory."""
    md = _harley_report(tmp_path, release=True)
    assert "Part A" in md and "Part B" in md and "Part C" in md
    assert "Harley Quinn" in md
    assert "not proof" in md
    assert "000000001" not in md          # SSID stripped in release
    # Bulk-dump fingerprint: a single commit carries all insertions.
    assert "single commit" in md.lower() or "dump" in md.lower()


def test_barbara_report_states_the_load_bearing_facts(tmp_path):
    """Part A/B/C structure + a PASS advisory for the human-looking repo."""
    md = _barbara_report(tmp_path, release=True)
    assert "Part A" in md and "Part B" in md and "Part C" in md
    assert "Barbara Gordon" in md
    assert "not proof" in md
    assert "000000002" not in md          # SSID stripped in release
    # Human fingerprint: a fix/revert commit appears in the ledger.
    assert "fix deadlock" in md or "revert" in md.lower()


# ---------------------------------------------------------------------------
# Tests — golden-file locks
# ---------------------------------------------------------------------------

def test_harley_release_matches_golden(tmp_path):
    md = _harley_report(tmp_path, release=True)
    golden_path = FIXT / "harley-quinn-release.golden.md"
    if not golden_path.exists() or os.environ.get("UPDATE_GOLDEN"):
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(md)
        pytest.skip("golden written; re-run to assert")
    assert _normalize(md) == _normalize(golden_path.read_text())


def test_barbara_release_matches_golden(tmp_path):
    md = _barbara_report(tmp_path, release=True)
    golden_path = FIXT / "barbara-gordon-release.golden.md"
    if not golden_path.exists() or os.environ.get("UPDATE_GOLDEN"):
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(md)
        pytest.skip("golden written; re-run to assert")
    assert _normalize(md) == _normalize(golden_path.read_text())


# ---------------------------------------------------------------------------
# Tests — pandoc PDF smoke test
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not shutil.which("pandoc"), reason="pandoc not installed")
def test_report_renders_to_pdf(tmp_path):
    """Smoke-test: pandoc/xelatex renders a synthetic report to a real (>1 KB) PDF."""
    from lectern.triage_report import to_pdf

    md = _barbara_report(tmp_path, release=True)
    md_p = tmp_path / "r.md"
    md_p.write_text(md)
    pdf_p = tmp_path / "r.pdf"
    to_pdf(md_p, pdf_p)
    assert pdf_p.exists(), "PDF file was not created"
    assert pdf_p.stat().st_size > 1000, f"PDF suspiciously small: {pdf_p.stat().st_size} bytes"

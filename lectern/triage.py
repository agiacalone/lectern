"""Triage module — CLI dispatcher for triage-related operations."""

from __future__ import annotations

import argparse
import csv as _csv
import hashlib
import subprocess
import sys
from collections import Counter
from pathlib import Path

from lectern.triage_version import SCHEMA_VERSION, SIGNAL_SET_VERSION


# ---------------------------------------------------------------------------
# Bucket ordering: FLAG is most urgent, PASS is least
# ---------------------------------------------------------------------------
_BUCKET_ORDER = {"FLAG": 0, "REVIEW": 1, "PASS": 2}
_FIELDS = ["name", "repo_url", "triage", "score", "grade", "reasoning"]


def _sorted_rows(rows):
    """Sort rows by triage bucket (FLAG first) then descending score."""
    return sorted(rows, key=lambda r: (_BUCKET_ORDER[r["triage"]], -r["score"]))


def write_results_csv(rows, path):
    """Write triage results to a CSV file, sorted by bucket then score."""
    with open(path, "w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=_FIELDS)
        w.writeheader()
        for r in _sorted_rows(rows):
            w.writerow({k: r.get(k, "") for k in _FIELDS})


def write_triage_md(rows, path, cfg):
    """Write a Markdown broadsheet triage report, sorted FLAG→REVIEW→PASS."""
    name = cfg["assignment"].get("name", "Results")
    rows = _sorted_rows(rows)
    lines = [
        f"# Authenticity Triage — {name}",
        "",
        "> 100% triage. A flag is a prompt to look, not a verdict. "
        "No student is penalized without human review.",
        "",
        "| Triage | Score | Student | Reasoning |",
        "|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['triage']} | {r['score']} | {r['name']} | {r['reasoning']} |")
    lines += [
        "",
        "---",
        "",
        f"*schema_version {cfg.get('schema_version', 1)} · signal_set {cfg.get('signal_set_version', 1)} · profile "
        f"{cfg.get('profile')} · engine {cfg.get('engine_sha', 'n/a')}*",
    ]
    Path(path).write_text("\n".join(lines) + "\n")


def engine_sha():
    """Return a 16-hex-char SHA-256 fingerprint over the engine source files."""
    here = Path(__file__).parent
    h = hashlib.sha256()
    for fn in ("triage_engine.py", "triage_signals.py"):
        p = here / fn
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Sweep helpers
# ---------------------------------------------------------------------------

def _discover_repos(run_dir):
    """Yield repo_dir for every *-submissions/*/ dir with .git."""
    run_dir = Path(run_dir)
    for submissions in run_dir.glob("*-submissions"):
        if not submissions.is_dir():
            continue
        for repo_dir in sorted(submissions.iterdir()):
            if repo_dir.is_dir() and (repo_dir / ".git").exists():
                yield repo_dir


def _score_one(repo_dir, cfg, roster):
    """Score a single repo dir and return a row dict."""
    from lectern.triage_engine import score_repo

    repo_prefix = cfg["assignment"].get("repo_prefix", "")
    basename = repo_dir.name
    github_username = (
        basename[len(repo_prefix):] if repo_prefix and basename.startswith(repo_prefix)
        else basename
    )

    # Resolve display name from roster, fall back to github username
    entry = roster.get(github_username, {})
    display_name = entry.get("display_name") or github_username

    # Get remote URL (best-effort)
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True,
        )
        repo_url = result.stdout.strip()
    except subprocess.CalledProcessError:
        repo_url = ""

    score, reasoning, bucket = score_repo(repo_dir, cfg, profile=cfg["profile"])
    return {
        "name": display_name,
        "repo_url": repo_url,
        "triage": bucket,
        "score": score,
        "grade": "",
        "reasoning": reasoning,
    }


def _run_scrape_clone(run_dir, org, prefix):
    """Clone student repos discovered via org-scrape (post-Classroom seam).

    Repos land in <run_dir>/scrape-submissions/<repo_name>/ so _discover_repos
    picks them up via the existing *-submissions/*/ glob unchanged.
    """
    from lectern.triage_scrape import discover_scrape_repos

    run_dir = Path(run_dir)
    submissions_dir = run_dir / "scrape-submissions"
    submissions_dir.mkdir(exist_ok=True)

    try:
        repo_names = discover_scrape_repos(org, prefix)
    except RuntimeError:
        raise

    if not repo_names:
        print(f"warning: no repos found in org {org!r} with prefix {prefix!r}", file=sys.stderr)
        return

    print(f"--- Cloning {len(repo_names)} repos via org-scrape ---")
    for name in repo_names:
        dest = submissions_dir / name
        if dest.is_dir() and (dest / ".git").exists():
            print(f"  pulling {name}...", end="", flush=True)
            result = subprocess.run(
                ["git", "-C", str(dest), "pull", "--quiet"],
                capture_output=True,
            )
            print("ok" if result.returncode == 0 else "FAILED")
        else:
            print(f"  cloning {name}...", end="", flush=True)
            try:
                subprocess.run(
                    ["gh", "repo", "clone", f"{org}/{name}", str(dest)],
                    capture_output=True, check=True,
                )
                print("ok")
            except FileNotFoundError:
                raise RuntimeError(
                    "gh CLI not found. Install it from https://cli.github.com/ "
                    "and authenticate with `gh auth login`."
                ) from None
            except subprocess.CalledProcessError as e:
                print(f"FAILED ({e.returncode})", file=sys.stderr)


def _run_clone(run_dir, classroom_assignment_id):
    """Clone student repos or pull existing ones. Mirrors triage.sh logic."""
    run_dir = Path(run_dir)
    existing = list(run_dir.glob("*-submissions"))
    if existing:
        print("--- Updating existing clones ---")
        for submissions in existing:
            for repo_dir in sorted(submissions.iterdir()):
                if repo_dir.is_dir() and (repo_dir / ".git").exists():
                    print(f"  pulling {repo_dir.name}...", end="", flush=True)
                    result = subprocess.run(
                        ["git", "-C", str(repo_dir), "pull", "--quiet"],
                        capture_output=True,
                    )
                    print("ok" if result.returncode == 0 else "FAILED")
    else:
        print("--- Cloning student repos ---")
        try:
            subprocess.run(
                [
                    "gh", "classroom", "clone", "student-repos",
                    "-a", str(classroom_assignment_id),
                    "--per-page", "100",
                ],
                cwd=str(run_dir),
                check=True,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "gh CLI not found. Install it from https://cli.github.com/ "
                "and authenticate with `gh auth login`."
            ) from None
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"gh classroom clone failed (exit {e.returncode}). "
                "Check that `gh auth status` is authenticated and the assignment ID is correct."
            ) from e


def _cmd_sweep(args):
    from lectern.triage_manifest import load_manifest
    from lectern.triage_engine import load_profile

    cfg = load_manifest(args.manifest)

    # Merge profile defaults (manifest overrides win)
    prof = load_profile(cfg["profile"])
    cfg["thresholds"] = {**prof["thresholds"], **cfg.get("thresholds", {})}
    cfg["weights"] = {**prof["weights"], **cfg.get("weights", {})}
    cfg["schema_version"] = SCHEMA_VERSION
    cfg["signal_set_version"] = SIGNAL_SET_VERSION
    cfg["engine_sha"] = engine_sha()

    run_dir = Path(args.run_dir)

    # Determine discovery mode: --scrape flag OR manifest source: scrape
    scrape_mode = getattr(args, "scrape", False) or cfg.get("source") == "scrape"

    # Clone / pull unless skipped
    if not args.skip_clone:
        if scrape_mode:
            print("Discovery mode: org-scrape (post-Classroom seam)")
            org = cfg["assignment"].get("org", "")
            prefix = cfg["assignment"].get("repo_prefix", "")
            if not org or not prefix:
                print(
                    "warning: assignment.org and assignment.repo_prefix must be set "
                    "in manifest for scrape mode; skipping clone.",
                    file=sys.stderr,
                )
            else:
                _run_scrape_clone(run_dir, org, prefix)
        else:
            print("Discovery mode: gh classroom clone")
            classroom_id = cfg["assignment"].get("classroom_assignment_id", 0)
            if not classroom_id:
                print(
                    "warning: classroom_assignment_id is 0 or unset in manifest; "
                    "skipping clone. Use --skip-clone to suppress this warning.",
                    file=sys.stderr,
                )
            else:
                _run_clone(run_dir, classroom_id)

    # Load roster (optional)
    roster = {}
    if args.github_csv:
        roster = load_roster_from_github_csv(args.github_csv)

    # Discover repos and score
    rows = []
    repos = list(_discover_repos(run_dir))
    print(f"--- Scoring {len(repos)} repos ---")
    for repo_dir in repos:
        try:
            row = _score_one(repo_dir, cfg, roster)
            rows.append(row)
            print(f"  {row['triage']:6s} {row['score']:3d}  {row['name']}")
        except Exception as e:
            print(f"  SKIP {repo_dir.name}: {e}", file=sys.stderr)
            continue

    # Write outputs
    csv_path = run_dir / "results.csv"
    md_path = run_dir / "TRIAGE.md"
    write_results_csv(rows, csv_path)
    write_triage_md(rows, md_path, cfg)

    # Summary
    counts = Counter(r["triage"] for r in rows)
    total = len(rows)
    print(
        f"\nDone: {total} repos — "
        f"FLAG {counts.get('FLAG', 0)} / "
        f"REVIEW {counts.get('REVIEW', 0)} / "
        f"PASS {counts.get('PASS', 0)}"
    )
    print(f"  wrote {csv_path}")
    print(f"  wrote {md_path}")
    return 0


def load_roster_from_github_csv(path):
    """Load a roster dict keyed by github_username from github.csv.

    Args:
        path: Path to github.csv (student_id, display_name, github_username).

    Returns:
        Dict mapping github_username -> {display_name, student_id}.
        Returns empty dict if file doesn't exist.
        Rows with empty github_username are skipped.
    """
    path = Path(path)
    if not path.exists():
        return {}
    with open(path) as f:
        return {r["github_username"]: {"display_name": r.get("display_name", ""),
                                       "student_id": r.get("student_id", "")}
                for r in _csv.DictReader(f) if r.get("github_username")}


def _resolve_grading_ref(repo: "Path", due_date: str, at: str | None) -> str:
    """Return the git ref to use for grading.

    If *at* is given, use it directly.  Otherwise, find the last commit
    on or before ``<due_date> 23:59:59``; fall back to HEAD if none found.
    """
    if at:
        return at
    result = subprocess.run(
        ["git", "-C", str(repo), "log",
         f"--before={due_date} 23:59:59", "-1", "--format=%H"],
        capture_output=True, text=True,
    )
    sha = result.stdout.strip()
    return sha if sha else "HEAD"


def _cmd_report(args):
    from lectern.triage_manifest import load_manifest
    from lectern.triage_engine import load_profile, score_repo
    from lectern.triage_report import deliverable_forensics, render_report
    from lectern.triage_signals import RepoFacts

    cfg = load_manifest(args.manifest)

    # Merge profile defaults (manifest values win over profile defaults)
    prof = load_profile(cfg["profile"])
    cfg["thresholds"] = {**prof["thresholds"], **cfg.get("thresholds", {})}
    cfg["weights"] = {**prof["weights"], **cfg.get("weights", {})}
    cfg["schema_version"] = SCHEMA_VERSION
    cfg["signal_set_version"] = SIGNAL_SET_VERSION
    cfg["engine_sha"] = engine_sha()

    repo = Path(args.repo)

    # Resolve student username: explicit positional wins; else derive from dir name
    if args.student:
        username = args.student
    else:
        repo_prefix = cfg["assignment"].get("repo_prefix", "")
        basename = repo.name
        if repo_prefix and basename.startswith(repo_prefix):
            username = basename[len(repo_prefix):]
        else:
            username = basename

    # Resolve student record from roster or synthesize minimal one
    roster = {}
    if args.github_csv:
        roster = load_roster_from_github_csv(args.github_csv)
    entry = roster.get(username, {})
    student = {
        "display_name": entry.get("display_name") or username,
        "student_id": entry.get("student_id", ""),
        "github_username": username,
    }

    asgn = cfg.get("assignment", {})
    # Resolve grading ref
    due_date = asgn.get("due_date", "")
    grading_ref = _resolve_grading_ref(repo, str(due_date), getattr(args, "at", None))

    # Gather facts, forensics, score
    facts = RepoFacts.from_repo(repo)
    forensics = deliverable_forensics(repo, cfg.get("deliverables", []),
                                      grading_ref=grading_ref)
    score = score_repo(repo, cfg, profile=cfg["profile"])

    md = render_report(student, cfg, facts, forensics, score,
                       release=args.release, grading_ref=grading_ref)

    out = Path(args.out)
    out.write_text(md)
    print(f"wrote {out}")
    return 0


def _cmd_rhythm(args):
    from lectern.triage_signals import RepoFacts
    from lectern.triage_rhythm import commit_fingerprint, rhythm_divergence, render_rhythm_report

    repo_paths = [Path(r) for r in args.repos]
    labels = [p.name for p in repo_paths]
    fingerprints = [commit_fingerprint(RepoFacts.from_repo(p)) for p in repo_paths]
    divergence = rhythm_divergence(fingerprints)
    md = render_rhythm_report(args.student, labels, fingerprints, divergence)
    out = Path(args.out)
    out.write_text(md)
    print(f"wrote {out}")
    return 0


def _cmd_init(args):
    # Defaults (static placeholders)
    term = args.term
    section = args.section
    assigned_date = "2026-01-01    # seed from term-spec; edit"
    due_date = "2026-01-15         # edit"

    # Term-spec seeding (when --term-spec is provided)
    if getattr(args, "term_spec", None):
        from lectern.term_spec import load_term_spec
        spec = load_term_spec(args.term_spec)
        matched = None
        for sec in spec.get("sections", []):
            if sec["course"] == args.course and str(sec["section"]) == str(args.section):
                matched = sec
                break
        if matched is not None:
            term = spec["term"]
            section = str(matched["section"])
            # spec dates load as datetime.date objects; coerce to ISO strings
            start = spec["start"]
            end = spec["end"]
            if hasattr(start, "isoformat"):
                start = start.isoformat()
            if hasattr(end, "isoformat"):
                end = end.isoformat()
            # Quote the date strings so YAML round-trips them as str, not date
            assigned_date = f'"{start}"'
            due_date = f'"{end}"'
        else:
            print(
                f"warning: no section matching course={args.course!r} section={args.section!r} "
                f"found in {args.term_spec}; using static placeholder dates.",
                file=sys.stderr,
            )

    stub = f"""assignment:
  course: "{args.course}"
  section: "{section}"
  term: {term}
  name: "{args.name}"
  classroom_assignment_id: 0   # gh classroom assignments --classroom-id <id>
  org: {args.org}
  repo_prefix: "{args.prefix}"
  assigned_date: {assigned_date}
  due_date: {due_date}
  total_points: 100
profile: {args.profile}
thresholds: {{}}
deliverables: []
"""
    Path(args.out).write_text(stub)
    print(f"wrote {args.out}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="reg-triage")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="scaffold a triage manifest")
    pi.add_argument("--course", required=True)
    pi.add_argument("--name", required=True)
    pi.add_argument("--section", default="01")
    pi.add_argument("--term", default="sp26")
    pi.add_argument("--org", default="Giacalone-CECS")
    pi.add_argument("--prefix", default="")
    pi.add_argument("--profile", default="short-project",
                    choices=["single-sitting", "short-project", "term-project"])
    pi.add_argument("--term-spec", default=None, dest="term_spec",
                    help="path to a term-spec YAML; seeds term, assigned_date, due_date")
    pi.add_argument("--out", required=True)
    pi.set_defaults(func=_cmd_init)

    ps = sub.add_parser("sweep", help="score all student repos and write results.csv + TRIAGE.md")
    ps.add_argument("--manifest", required=True, help="path to *.triage.yaml manifest")
    ps.add_argument("--github-csv", default=None, dest="github_csv",
                    help="optional path to github.csv roster for display-name resolution")
    ps.add_argument("--run-dir", default=".", dest="run_dir",
                    help="directory where *-submissions/ dirs live (default: .)")
    ps.add_argument("--skip-clone", action="store_true", dest="skip_clone",
                    help="skip gh classroom clone / git pull step")
    ps.add_argument("--scrape", action="store_true", dest="scrape",
                    help="use org-scrape repo discovery instead of gh classroom clone "
                         "(post-Classroom decommission 2026-08-28 seam)")
    ps.set_defaults(func=_cmd_sweep)

    pr = sub.add_parser("report",
                        help="generate a two-tier authenticity report for one student repo")
    pr.add_argument("student", nargs="?", default=None,
                    help="github username (optional; derived from repo dir name if omitted)")
    pr.add_argument("--manifest", required=True, help="path to *.triage.yaml manifest")
    pr.add_argument("--repo", required=True, help="path to the local clone of the student repo")
    pr.add_argument("--github-csv", default=None, dest="github_csv",
                    help="optional path to github.csv roster for display-name / student-id lookup")
    pr.add_argument("--out", required=True, help="output .md path")
    pr.add_argument("--release", action="store_true",
                    help="omit SSID and sanitize Obsidian-isms for release variant")
    pr.add_argument("--at", default=None,
                    help="git ref to use as grading commit (default: last commit on or before due_date)")
    pr.set_defaults(func=_cmd_report)

    prh = sub.add_parser("rhythm",
                         help="cross-assignment commit-rhythm advisory for one student")
    prh.add_argument("--student", required=True, help="student github username")
    prh.add_argument("--repos", nargs="+", required=True,
                     help="local repo paths (one per assignment, in order)")
    prh.add_argument("--out", required=True, help="output .md path")
    prh.set_defaults(func=_cmd_rhythm)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

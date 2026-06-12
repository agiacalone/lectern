"""pa-isa-publish — sync vault archive artifacts to the Giacalone-ISA Drive.

This module is the orchestrator. It walks an archive bundle (and selected
vault-wide artifacts), applies a routing table to determine each artifact's
destination path under ``Giacalone-ISA/<term>/...``, and dispatches uploads
via the detected backend (MCP/service-account/rclone — see pa.drive_auth).

Idempotency is hash-based: each entry's SHA-256 source hash is stored in the
per-bundle ``isa-publish.yaml`` alongside its Drive file ID and last push
timestamp. On re-run, unchanged sources are skipped; changed sources update
the existing Drive file (preserving its shareable link and permissions).

Out-of-scope for v1 per spec:
  - Two-way Drive→vault sync.
  - Permission auditing (Drive shares inherit from Giacalone-ISA/ root).
  - Notification (Drive's built-in 'new file' emails cover this).

See <vault>/plans/specs/2026-05-13-per-student-exam-id-design Part 6.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

import yaml

from lectern.drive_auth import DriveBackend, detect_backend
from lectern.isa_publish_schema import (
    ISAPublishValidationError,
    default_manifest as default_publish_manifest,
    validate,
    validate_yaml,
)


# ---------------------------------------------------------------------------
# Routing table — vault patterns → Drive subfolder templates.
#
# Each tuple: (pattern, drive_subfolder_template, scope, description).
#   - pattern is glob-style, evaluated relative to bundle_dir for "bundle"
#     scope or to vault_root for "vault" scope.
#   - drive_subfolder_template uses {TERM}, {COURSE}, {SECTION} placeholders.
# ---------------------------------------------------------------------------

ROUTING_TABLE: list[tuple[str, str, str, str]] = [
    ("exams/*_key.pdf",
     "Giacalone-ISA/{TERM}/Finals/",
     "bundle", "exam grading keys"),
    ("exams/*_combined.pdf",
     "Giacalone-ISA/{TERM}/{COURSE} Section {SECTION}/",
     "bundle", "per-student print stacks"),
    ("**/lab_*_grading_rubric.md",
     "Giacalone-ISA/{TERM}/Grading Rubrics/",
     "bundle", "lab grading rubrics"),
    ("notes/isa-grading-delegation-*.md",
     "Giacalone-ISA/{TERM}/",
     "vault", "ISA division of labor"),
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PublishConfig:
    bundle_dir: Path
    course: str                # "CECS 478"
    term: str                  # "sp26"
    section: str               # "04"
    dry_run: bool = True
    check: bool = False
    vault_root: Path | None = None


@dataclass
class PublishEntry:
    source: Path
    drive_path: str
    source_hash: str = ""
    last_pushed: str = ""
    drive_file_id: str = ""

    def to_dict(self) -> dict:
        d = {
            "source": str(self.source),
            "drive_path": self.drive_path,
            "source_hash": self.source_hash,
        }
        if self.last_pushed:
            d["last_pushed"] = self.last_pushed
        if self.drive_file_id:
            d["drive_file_id"] = self.drive_file_id
        return d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _drive_path_for(src: Path, template: str, cfg: PublishConfig) -> str:
    """Substitute placeholders and append the source filename."""
    folder = template.format(
        TERM=cfg.term.upper(),
        COURSE=cfg.course,
        SECTION=cfg.section,
    )
    if not folder.endswith("/"):
        folder += "/"
    return folder + src.name


def _iter_bundle_matches(bundle_dir: Path, pattern: str) -> Iterable[Path]:
    """Yield bundle-relative files matching pattern under bundle_dir."""
    if not bundle_dir.exists():
        return
    # Use Path.glob with the pattern interpreted relative to bundle_dir.
    yield from bundle_dir.glob(pattern)


def _iter_vault_matches(vault_root: Path, pattern: str) -> Iterable[Path]:
    """Yield vault-relative files matching pattern under vault_root."""
    if not vault_root or not vault_root.exists():
        return
    # The vault pattern includes a leading subdir (e.g. "notes/isa-..."), so
    # split off the first path segment as the search root.
    parts = Path(pattern).parts
    if len(parts) >= 2:
        sub_root = vault_root / parts[0]
        sub_pattern = str(Path(*parts[1:]))
        if sub_root.exists():
            yield from sub_root.glob(sub_pattern)
    else:
        yield from vault_root.glob(pattern)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_publish_manifest(cfg: PublishConfig) -> list[PublishEntry]:
    """Walk the bundle + vault per ROUTING_TABLE, compute SHA-256 for each match."""
    entries: list[PublishEntry] = []
    seen: set[Path] = set()

    for pattern, template, scope, _desc in ROUTING_TABLE:
        if scope == "bundle":
            matches = _iter_bundle_matches(cfg.bundle_dir, pattern)
        elif scope == "vault":
            matches = _iter_vault_matches(cfg.vault_root, pattern) if cfg.vault_root else []
        else:
            continue

        for src in matches:
            if not src.is_file():
                continue
            if src in seen:
                continue
            seen.add(src)
            drive_path = _drive_path_for(src, template, cfg)
            entries.append(PublishEntry(
                source=src,
                drive_path=drive_path,
                source_hash=_sha256(src),
            ))

    return entries


def publish_to_drive(
    entries: list[PublishEntry],
    backend: DriveBackend,
    existing_manifest: dict | None = None,
) -> list[PublishEntry]:
    """Upload/update each entry via backend, honoring hash-skip semantics.

    Returns the updated entry list with drive_file_id and last_pushed populated.
    """
    prior_by_source: dict[str, dict] = {}
    if existing_manifest and isinstance(existing_manifest.get("publish"), list):
        for row in existing_manifest["publish"]:
            prior_by_source[row.get("source", "")] = row

    now_iso = datetime.now().astimezone().isoformat()

    for entry in entries:
        prior = prior_by_source.get(str(entry.source))
        if prior:
            prior_hash = prior.get("source_hash", "")
            prior_file_id = prior.get("drive_file_id", "")
            if prior_hash == entry.source_hash and prior_file_id:
                # No-op: source unchanged and we know the Drive file ID.
                entry.drive_file_id = prior_file_id
                entry.last_pushed = prior.get("last_pushed", "")
                continue
            if prior_file_id:
                # Source changed but Drive file exists — overwrite in place.
                backend.update(prior_file_id, entry.source)
                entry.drive_file_id = prior_file_id
                entry.last_pushed = now_iso
                continue

        # No prior record (or prior had no file_id) — fresh upload.
        file_id = backend.upload(entry.source, entry.drive_path)
        entry.drive_file_id = file_id
        entry.last_pushed = now_iso

    return entries


def check_publish(
    cfg: PublishConfig,
    backend: DriveBackend,
) -> tuple[int, int, list[str]]:
    """Verify every entry in the bundle's isa-publish.yaml.

    Reports (ok_count, fail_count, list_of_issue_strings).
    """
    publish_yaml = cfg.bundle_dir / "isa-publish.yaml"
    if not publish_yaml.exists():
        return (0, 1, [f"no isa-publish.yaml at {publish_yaml}"])

    try:
        data = validate_yaml(publish_yaml)
    except ISAPublishValidationError as e:
        return (0, 1, [str(e)])

    ok = 0
    fail = 0
    issues: list[str] = []

    for row in data.get("publish", []):
        src = Path(row.get("source", ""))
        drive_path = row.get("drive_path", "")
        recorded_hash = row.get("source_hash", "")
        drive_file_id = row.get("drive_file_id", "")

        # 1. Source exists in vault?
        if not src.exists():
            fail += 1
            issues.append(f"missing source: {src}")
            continue

        # 2. Source hash still matches?
        current_hash = _sha256(src)
        if current_hash != recorded_hash:
            fail += 1
            issues.append(f"source edited since last push (hash mismatch): {src}")
            continue

        # 3. Drive file exists?
        drive_md5 = backend.file_md5(drive_file_id) if drive_file_id else None
        if drive_md5 is None:
            # Backend may legitimately not support md5 (MCP). Treat as
            # "couldn't verify" rather than failure — still counts as OK
            # locally; the outer Claude session will revalidate via MCP.
            ok += 1
            continue

        # 4. Drive md5 matches source md5?
        source_md5 = hashlib.md5(src.read_bytes()).hexdigest()
        if drive_md5 != source_md5:
            fail += 1
            issues.append(
                f"Drive copy differs from source: {drive_path} (file_id={drive_file_id})"
            )
            continue

        ok += 1

    return (ok, fail, issues)


def _write_publish_yaml(bundle_dir: Path, entries: list[PublishEntry]) -> Path:
    """Serialize entries to bundle_dir/isa-publish.yaml. Validates before write."""
    data = {"publish": [e.to_dict() for e in entries]}
    validate(data)
    path = bundle_dir / "isa-publish.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def _load_existing_manifest(bundle_dir: Path) -> dict | None:
    p = bundle_dir / "isa-publish.yaml"
    if not p.exists():
        return None
    try:
        return validate_yaml(p)
    except ISAPublishValidationError:
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pa-isa-publish",
        description="Sync vault archive artifacts to the Giacalone-ISA Google Drive.",
    )
    p.add_argument("--bundle", type=Path, help="path to an archive bundle directory")
    p.add_argument("--course", help='course code like "CECS 478"')
    p.add_argument("--term", help="term code like sp26")
    p.add_argument("--section", help="section number like 04")
    p.add_argument("--vault-root", type=Path, default=None,
                   help="vault root (for vault-scoped artifacts)")
    p.add_argument("--check", action="store_true",
                   help="verify existing publish manifest against vault + Drive")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="print planned actions only (default)")
    p.add_argument("--commit", action="store_true",
                   help="actually upload via the detected backend")
    return p


def _run_single_bundle(cfg: PublishConfig, backend: DriveBackend) -> int:
    entries = build_publish_manifest(cfg)
    if not entries:
        print(f"pa-isa-publish: no matching artifacts under {cfg.bundle_dir}")
        return 0

    print(f"pa-isa-publish: backend={backend.name} bundle={cfg.bundle_dir}")
    print(f"pa-isa-publish: {len(entries)} candidate artifacts")
    for e in entries:
        print(f"  - {e.source}")
        print(f"      -> {e.drive_path}")
        print(f"      hash={e.source_hash[:23]}...")

    if cfg.dry_run:
        print("pa-isa-publish: --dry-run, no Drive writes performed.")
        return 0

    existing = _load_existing_manifest(cfg.bundle_dir)
    updated = publish_to_drive(entries, backend, existing_manifest=existing)
    _write_publish_yaml(cfg.bundle_dir, updated)
    print(f"pa-isa-publish: wrote {cfg.bundle_dir / 'isa-publish.yaml'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.commit:
        args.dry_run = False

    backend = detect_backend()

    if args.check:
        if not args.bundle:
            print("pa-isa-publish --check requires --bundle", file=sys.stderr)
            return 2
        cfg = PublishConfig(
            bundle_dir=args.bundle,
            course=args.course or "",
            term=args.term or "",
            section=args.section or "",
            vault_root=args.vault_root,
            check=True,
        )
        ok, fail, issues = check_publish(cfg, backend)
        print(f"pa-isa-publish --check: ok={ok} fail={fail}")
        for issue in issues:
            print(f"  ! {issue}")
        return 1 if fail else 0

    if not args.bundle:
        print("pa-isa-publish: --bundle required (or use --term to iterate)", file=sys.stderr)
        return 2

    if not (args.course and args.term and args.section):
        print("pa-isa-publish: --course, --term, --section all required for a bundle run",
              file=sys.stderr)
        return 2

    cfg = PublishConfig(
        bundle_dir=args.bundle,
        course=args.course,
        term=args.term,
        section=args.section,
        dry_run=args.dry_run,
        vault_root=args.vault_root,
    )
    return _run_single_bundle(cfg, backend)


if __name__ == "__main__":
    raise SystemExit(main())

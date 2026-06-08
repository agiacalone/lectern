"""``reg-term-finalize`` — reconcile + flip + roll up a term at grade-submission.

For each section of ``--term`` (discovered by globbing class notes):
  1. reconcile the manifest's ``grades.distribution`` / ``dfw_rate`` against the
     bundle's ``gradebook.csv`` (backing up the manifest before any change);
  2. flip the class-note frontmatter to ``status: finalized`` (frontmatter-only
     edit — the body, including the reflection, is preserved);
  3. roll up enrollment-weighted aggregates onto the semester note and flip it
     to ``finalized`` too.

``--dry-run`` computes and prints everything but writes nothing.
``--allow-missing`` lets sections without a ``gradebook.csv`` still flip status
(skipping their reconcile) instead of aborting the whole run.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

from lectern import gradebook
from lectern.vault_notes import split_frontmatter, set_frontmatter_fields


def _now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _discover_sections(vault: Path, term: str) -> list[Path]:
    out = []
    for p in sorted((vault / "classes").glob(f"**/*-{term}.md")):
        try:
            fm, _ = split_frontmatter(p.read_text())
        except ValueError:
            continue
        if fm.get("type") == "class-note" and str(fm.get("term")) == term:
            out.append(p)
    return out


def _reconcile_manifest(bundle: Path, dist: dict, dry_run: bool) -> tuple[dict, bool]:
    """Return (manifest dict, changed?). Backs up + writes unless dry-run."""
    man_path = bundle / "manifest.yaml"
    man = yaml.safe_load(man_path.read_text()) or {}
    grades = man.setdefault("grades", {})
    new_dist = dist["distribution"]
    new_dfw = round(dist["dfw_rate"], 3)
    changed = grades.get("distribution") != new_dist or grades.get("dfw_rate") != new_dfw
    if changed and not dry_run:
        shutil.copy2(man_path, bundle / f"manifest.yaml.bak-{date.today().isoformat()}")
        grades["distribution"] = new_dist
        grades["dfw_rate"] = new_dfw
        man_path.write_text(yaml.dump(man, sort_keys=False, allow_unicode=True))
    else:
        grades["distribution"] = new_dist
        grades["dfw_rate"] = new_dfw
    return man, changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reg-term-finalize")
    ap.add_argument("--term", required=True)
    ap.add_argument("--vault-root", required=True, type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-missing", action="store_true")
    args = ap.parse_args(argv)

    vault = args.vault_root
    term = args.term
    dry = args.dry_run

    sections = _discover_sections(vault, term)
    if not sections:
        print(f"no class notes found for term {term}", file=sys.stderr)
        return 1

    # First pass: validate gradebooks exist (unless --allow-missing).
    section_info = []  # (class_note_path, bundle, has_gradebook)
    for cn in sections:
        fm, _ = split_frontmatter(cn.read_text())
        # bundle: archives/<term>-<section>/ next to the course folder
        sec = str(fm.get("section"))
        bundle = cn.parent / "archives" / f"{term}-{sec}"
        gb = bundle / "gradebook.csv"
        if not gb.exists():
            if not args.allow_missing:
                print(f"missing gradebook: {gb}", file=sys.stderr)
                return 1
            section_info.append((cn, bundle, False))
        else:
            section_info.append((cn, bundle, True))

    enrolled_sum = 0
    completed_sum = 0
    withdrew_sum = 0
    dfw_weighted = 0.0

    for cn, bundle, has_gb in section_info:
        fm, _ = split_frontmatter(cn.read_text())
        sec = str(fm.get("section"))
        dfw = float(fm.get("dfw-rate") or 0)
        man = None

        if has_gb:
            dist = gradebook.grade_distribution(bundle / "gradebook.csv")
            man, changed = _reconcile_manifest(bundle, dist, dry)
            dfw = round(dist["dfw_rate"], 3)
            verb = "would reconcile" if (changed and dry) else (
                "reconciled" if changed else "clean")
            print(f"{cn.name}: dist={dist['distribution']} dfw={dfw} [{verb}]")
        else:
            print(f"{cn.name}: gradebook missing — status flip only")

        head = (man or {}).get("headcount", {}) if man else {}
        enrolled = head.get("enrolled", fm.get("headcount", {}).get("enrolled", 0))
        completed = head.get("completed", fm.get("headcount", {}).get("completed", 0))
        withdrew = head.get("withdrew", fm.get("headcount", {}).get("withdrew", 0))

        updates = {
            "status": "finalized",
            "dfw-rate": dfw,
            "headcount.enrolled": enrolled,
            "headcount.completed": completed,
            "headcount.withdrew": withdrew,
            "updated": _now_iso(),
        }
        if not dry:
            cn.write_text(set_frontmatter_fields(cn.read_text(), updates))

        enrolled_sum += int(enrolled or 0)
        completed_sum += int(completed or 0)
        withdrew_sum += int(withdrew or 0)
        dfw_weighted += float(dfw) * int(enrolled or 0)

    overall_dfw = round(dfw_weighted / enrolled_sum, 3) if enrolled_sum else 0.0
    sem_path = vault / "classes" / f"{term}.md"
    print(f"\nrollup: enrolled={enrolled_sum} completed={completed_sum} "
          f"withdrew={withdrew_sum} overall-dfw={overall_dfw}")
    if sem_path.exists() and not dry:
        sem_path.write_text(set_frontmatter_fields(sem_path.read_text(), {
            "total-enrolled": enrolled_sum,
            "total-completed": completed_sum,
            "total-withdrew": withdrew_sum,
            "overall-dfw-rate": overall_dfw,
            "status": "finalized",
            "updated": _now_iso(),
        }))

    if dry:
        print("\n--dry-run: no files written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

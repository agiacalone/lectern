"""pa-exam-verify — confirm a per-student exam PDF matches its claimed name.

Extracts ``Serial`` + (optional) ``ID`` from page 1's footer, recomputes the
expected ``student_serial`` from the printed source_serial + canonical(name),
and confirms they match. Closes the forensic loop on per-student exam IDs:

  - variant Serial proves which source a printed page came from
  - per-student ID proves which printed copy a page came from
  - this verifier confirms the printed ID actually hashes from the printed
    Serial + the claimed student name (catches swaps, forgery, mis-prints)

See docs/design/per-student-exam-id-design Part 1 §Verification.
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from lectern.exam_serial import student_serial


# ----- data ---------------------------------------------------------------


@dataclass
class VerifyResult:
    ok: bool
    printed_source: str
    printed_student: str | None
    computed_student: str | None
    student_name: str | None


# Primary regex: tolerates U+00B7 MIDDLE DOT (LaTeX \textperiodcentered) or
# U+2022 BULLET, plus a fallback that allows just whitespace between Serial and
# ID (in case pdftotext strips the separator).
_FOOTER_RE_PRIMARY = re.compile(
    r"Serial\s+([A-F0-9]{8})(?:\s*[·•]\s*ID\s+([A-F0-9]{8}))?"
)
_FOOTER_RE_FALLBACK = re.compile(
    r"Serial\s+([A-F0-9]{8})(?:\s+ID\s+([A-F0-9]{8}))?"
)


# ----- extraction ---------------------------------------------------------


def _extract_text_pdfplumber(pdf: Path) -> str:
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        return ""
    try:
        with pdfplumber.open(pdf) as f:
            if not f.pages:
                return ""
            return f.pages[0].extract_text() or ""
    except Exception:
        return ""


def _extract_text_pdftotext(pdf: Path) -> str:
    """Fallback if pdfplumber returns nothing useful."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", "-f", "1", "-l", "1", str(pdf), "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout or ""
    except FileNotFoundError:
        return ""


def extract_footer_serials(pdf: Path) -> dict:
    """Read PDF page 1, extract Serial (and optional ID) from footer.

    Returns ``{"source": "8HEX", "student": "8HEX" | None}``.
    Raises SystemExit if no Serial is found.
    """
    if not pdf.is_file():
        raise SystemExit(f"pa-exam-verify: not found: {pdf}")

    text = _extract_text_pdfplumber(pdf)
    match = _FOOTER_RE_PRIMARY.search(text) or _FOOTER_RE_FALLBACK.search(text)
    if not match:
        # Fall back to pdftotext
        text = _extract_text_pdftotext(pdf)
        match = _FOOTER_RE_PRIMARY.search(text) or _FOOTER_RE_FALLBACK.search(text)
    if not match:
        raise SystemExit(
            f"pa-exam-verify: no Serial found in footer of {pdf} — "
            "is this an exam PDF produced by pa-exam-build?"
        )
    return {"source": match.group(1), "student": match.group(2)}


# ----- verification -------------------------------------------------------


def verify_pdf(pdf: Path, student_name: str) -> VerifyResult:
    """Verify a per-student PDF's printed ID matches the expected hash."""
    serials = extract_footer_serials(pdf)
    src = serials["source"]
    printed = serials["student"]
    if printed is None:
        return VerifyResult(
            ok=False,
            printed_source=src,
            printed_student=None,
            computed_student=None,
            student_name=student_name,
        )
    computed = student_serial(src, student_name)
    return VerifyResult(
        ok=(computed == printed),
        printed_source=src,
        printed_student=printed,
        computed_student=computed,
        student_name=student_name,
    )


def verify_register(
    register_csv: Path, pdf_dir: Path
) -> tuple[int, int, list[str]]:
    """Bulk-verify all PDFs listed in a register CSV.

    Returns ``(ok_count, fail_count, issues)``.
    """
    if not register_csv.is_file():
        raise SystemExit(f"pa-exam-verify: register not found: {register_csv}")

    ok_count = 0
    fail_count = 0
    issues: list[str] = []
    with register_csv.open() as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        name = row.get("name", "")
        pdf_name = row.get("output_pdf", "")
        pdf_path = pdf_dir / pdf_name
        if not pdf_path.is_file():
            fail_count += 1
            issues.append(f"missing: {pdf_name} ({name})")
            continue
        try:
            r = verify_pdf(pdf_path, name)
        except SystemExit as e:
            fail_count += 1
            issues.append(f"extract failed: {pdf_name} ({name}): {e}")
            continue
        if r.ok:
            ok_count += 1
        else:
            fail_count += 1
            if r.printed_student is None:
                issues.append(
                    f"variant-only PDF (no student ID in footer): {pdf_name} ({name})"
                )
            else:
                issues.append(
                    f"mismatch: {pdf_name} ({name}): "
                    f"printed={r.printed_student} computed={r.computed_student}"
                )
    return ok_count, fail_count, issues


# ----- CLI ----------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pa-exam-verify",
        description="Verify per-student exam PDF IDs against printed Serial + claimed name.",
    )
    p.add_argument("--student", type=str, default=None, help="claimed student name (with --pdf)")
    p.add_argument("--pdf", type=Path, default=None, help="single PDF to verify (with --student)")
    p.add_argument("--register", type=Path, default=None, help="register CSV for bulk verify (with --dir)")
    p.add_argument("--dir", type=Path, default=None, help="directory holding PDFs (with --register)")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    single_mode = args.student is not None and args.pdf is not None
    bulk_mode = args.register is not None and args.dir is not None

    if single_mode == bulk_mode:
        parser.error(
            "pick exactly one mode: --student NAME --pdf FILE  OR  --register CSV --dir DIR"
        )

    if single_mode:
        try:
            r = verify_pdf(args.pdf, args.student)
        except SystemExit as e:
            print(str(e), file=sys.stderr)
            return 2
        if r.ok:
            print(f"OK: {args.pdf.name} matches {r.student_name} (ID {r.printed_student})")
            return 0
        if r.printed_student is None:
            print(
                f"FAIL: {args.pdf.name} is variant-only (no student ID in footer); "
                f"source serial={r.printed_source}",
                file=sys.stderr,
            )
        else:
            print(
                f"FAIL: {args.pdf.name} ({r.student_name}): "
                f"printed={r.printed_student} computed={r.computed_student}",
                file=sys.stderr,
            )
        return 1

    # bulk
    ok, fail, issues = verify_register(args.register, args.dir)
    print(f"✓ {ok}  ✗ {fail}")
    for issue in issues:
        print(f"  {issue}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

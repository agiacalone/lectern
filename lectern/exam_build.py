"""pa-exam-build — compile exam .tex into PDFs.

Three modes:
  - Variant (default): <exam>.pdf + <exam>_key.pdf
  - Roster (--roster): N student PDFs + register CSV + 1 key
  - Combined (--combined, with --roster): also produce <exam>_combined.pdf

The per-student build injects \\def\\studentname / \\def\\studentserial via
the command line. The exam .tex must define empty defaults for both macros
(via \\@ifundefined+\\def or \\providecommand). See A.2 doctrine.

See <vault>/plans/specs/2026-05-13-per-student-exam-id-design Part 1.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from lectern.exam_serial import canonical_name, source_serial_from_tex, student_serial
from lectern._text import slugify


# ----- dataclasses ---------------------------------------------------------


@dataclass
class ExamBuildConfig:
    source: Path
    roster: Path | None = None
    combined: bool = False
    register_out: Path | None = None


@dataclass
class BuildResult:
    source_serial: str
    student_pdfs: list[Path] = field(default_factory=list)
    key_pdf: Path | None = None
    register_csv: Path | None = None
    combined_pdf: Path | None = None


# ----- helpers -------------------------------------------------------------


_AUX_EXTS = (".aux", ".log", ".out", ".toc")


def _tex_escape(value: str) -> str:
    """Very light LaTeX escape for values injected via \\def (names, IDs).

    Backslash and braces are the dangerous chars; roster names are mostly plain
    text + accents and IDs are digits, so this is deliberately minimal.
    """
    return (
        value.replace("\\", r"\textbackslash{}")
        .replace("{", r"\{")
        .replace("}", r"\}")
    )


def _cleanup_aux(workdir: Path, stem: str) -> None:
    for ext in _AUX_EXTS:
        p = workdir / f"{stem}{ext}"
        p.unlink(missing_ok=True)


def _run_pdflatex(
    workdir: Path,
    source_filename: str,
    jobname: str,
    pre_input: str = "",
) -> None:
    """Run pdflatex twice for refs/TOC stabilization.

    pre_input is a TeX fragment injected before \\input{source} (used for
    per-student \\def\\studentname / \\def\\studentserial, and for the key
    build's \\def\\answersmode{1}).
    """
    if pre_input:
        tex_arg = f"{pre_input}\\input{{{source_filename}}}"
    else:
        tex_arg = source_filename

    cmd = [
        "pdflatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-jobname={jobname}",
        tex_arg,
    ]
    for _ in range(2):
        result = subprocess.run(
            cmd,
            cwd=workdir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            sys.stderr.write(result.stdout)
            sys.stderr.write(result.stderr)
            raise SystemExit(
                f"pa-exam-build: pdflatex failed for jobname={jobname}"
            )


def _check_per_student_macros(tex_content: str) -> bool:
    """True if both \\studentname and \\studentserial have a macro-defaulting
    pattern present somewhere in the file.

    Tolerates both \\providecommand{\\studentname}{...} and
    \\@ifundefined{studentname}{\\def\\studentname{...}}{...} forms.
    """
    for macro in ("studentname", "studentserial"):
        has_providecommand = (
            f"\\providecommand{{\\{macro}}}" in tex_content
        )
        has_ifundefined = (
            f"\\@ifundefined{{{macro}}}" in tex_content
        )
        if not (has_providecommand or has_ifundefined):
            return False
    return True


def _concat_pdfs(inputs: list[Path], out: Path) -> None:
    """Concatenate PDFs using pdfunite or qpdf, whichever is available."""
    if shutil.which("pdfunite"):
        cmd = ["pdfunite", *(str(p) for p in inputs), str(out)]
    elif shutil.which("qpdf"):
        cmd = ["qpdf", "--empty", "--pages", *(str(p) for p in inputs), "--", str(out)]
    else:
        raise SystemExit(
            "pa-exam-build: neither pdfunite nor qpdf is installed.\n"
            "  Install one of:\n"
            "    sudo dnf install poppler-utils    # provides pdfunite\n"
            "    sudo dnf install qpdf\n"
            "    sudo apt install poppler-utils    # debian/ubuntu\n"
            "    sudo apt install qpdf"
        )
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(f"pa-exam-build: PDF concat failed ({cmd[0]})")


def _read_roster(roster_path: Path) -> list[dict[str, str]]:
    """Parse roster CSV, return list of {"name", "student_id"} dicts.

    Validates a 'name' column + non-empty cells. A 'student_id' column is
    OPTIONAL — when absent, student_id is "" (the exam's STUDENT ID# line is
    then left blank for the student to write in). Detects fully-blank lines
    (which csv.DictReader silently skips) and treats them as empty-name errors
    so the user notices stray blank rows.
    """
    raw_lines = roster_path.read_text().splitlines()
    if not raw_lines:
        raise SystemExit(f"pa-exam-build: roster {roster_path} is empty")

    # Parse header to find name + (optional) student_id column indices
    header_reader = csv.reader([raw_lines[0]])
    header = next(header_reader)
    name_idx = None
    sid_idx = None
    for i, col in enumerate(header):
        key = col.strip().lower()
        if key == "name":
            name_idx = i
        elif key == "student_id":
            sid_idx = i
    if name_idx is None:
        raise SystemExit(
            f"pa-exam-build: roster {roster_path} missing 'name' column"
            f" (headers: {header})"
        )

    rows: list[dict[str, str]] = []
    # Header is line 1; data rows start at line 2
    for lineno, raw in enumerate(raw_lines[1:], start=2):
        if not raw.strip():
            raise SystemExit(
                f"pa-exam-build: empty name at line {lineno} of {roster_path}"
            )
        fields = next(csv.reader([raw]))
        name = (fields[name_idx] if name_idx < len(fields) else "").strip()
        if not name:
            raise SystemExit(
                f"pa-exam-build: empty name at line {lineno} of {roster_path}"
            )
        sid = ""
        if sid_idx is not None and sid_idx < len(fields):
            sid = fields[sid_idx].strip()
        rows.append({"name": name, "student_id": sid})

    if not rows:
        raise SystemExit(f"pa-exam-build: roster {roster_path} has no rows")
    return rows


# ----- public API ----------------------------------------------------------


def build_variant(cfg: ExamBuildConfig) -> BuildResult:
    """Build <exam>.pdf + <exam>_key.pdf (variant-only mode)."""
    src = cfg.source.resolve()
    if not src.is_file():
        raise SystemExit(f"pa-exam-build: not found: {src}")
    workdir = src.parent
    stem = src.stem
    source_filename = src.name

    tex_content = src.read_text()
    src_serial = source_serial_from_tex(tex_content)

    student_pdf = workdir / f"{stem}.pdf"
    key_pdf = workdir / f"{stem}_key.pdf"
    student_pdf.unlink(missing_ok=True)
    key_pdf.unlink(missing_ok=True)

    # student build — inject canonical \examserial so printed footer matches
    # source_serial_from_tex(content) by builder construction.
    _run_pdflatex(
        workdir,
        source_filename,
        jobname=stem,
        pre_input=rf"\def\examserial{{{src_serial}}}",
    )
    _cleanup_aux(workdir, stem)

    # key build
    _run_pdflatex(
        workdir,
        source_filename,
        jobname=f"{stem}_key",
        pre_input=rf"\def\answersmode{{1}}\def\examserial{{{src_serial}}}",
    )
    _cleanup_aux(workdir, f"{stem}_key")

    return BuildResult(
        source_serial=src_serial,
        student_pdfs=[student_pdf],
        key_pdf=key_pdf,
    )


def build_roster(cfg: ExamBuildConfig) -> BuildResult:
    """Build N student PDFs (one per roster row) + 1 key + register CSV."""
    if cfg.roster is None:
        raise SystemExit("pa-exam-build: build_roster requires cfg.roster")
    src = cfg.source.resolve()
    if not src.is_file():
        raise SystemExit(f"pa-exam-build: not found: {src}")
    workdir = src.parent
    stem = src.stem
    source_filename = src.name

    tex_content = src.read_text()
    if not _check_per_student_macros(tex_content):
        raise SystemExit(
            "pa-exam-build: source .tex lacks per-student macros — regenerate"
            " from lecture-materials-assistant or hand-patch the preamble per"
            " <vault>/plans/specs/2026-05-13-per-student-exam-id-design"
            " § Backward-Compat Gotcha."
        )

    src_serial = source_serial_from_tex(tex_content)
    roster_rows = _read_roster(cfg.roster)

    # Build key once (variant-level, no \studentname injection)
    key_pdf = workdir / f"{stem}_key.pdf"
    key_pdf.unlink(missing_ok=True)
    _run_pdflatex(
        workdir,
        source_filename,
        jobname=f"{stem}_key",
        pre_input=rf"\def\answersmode{{1}}\def\examserial{{{src_serial}}}",
    )
    _cleanup_aux(workdir, f"{stem}_key")

    # Build one PDF per student
    register_rows: list[dict[str, str]] = []
    student_pdfs: list[Path] = []
    for row in roster_rows:
        name = row["name"]
        sid = row.get("student_id", "")
        ssn = student_serial(src_serial, name)
        name_slug = slugify(name)
        jobname = f"{stem}_{name_slug}_{ssn}"
        out_pdf = workdir / f"{jobname}.pdf"
        out_pdf.unlink(missing_ok=True)

        # LaTeX-escape name + student_id for \def (very light — backslash and
        # braces are the dangerous chars; roster names are mostly plain text +
        # accents, IDs are digits). \studentid is injected so the exam template
        # can pre-fill the STUDENT ID# line; empty when the roster omits it.
        safe_name = _tex_escape(name)
        safe_sid = _tex_escape(sid)
        pre_input = (
            rf"\def\examserial{{{src_serial}}}"
            rf"\def\studentname{{{safe_name}}}"
            rf"\def\studentid{{{safe_sid}}}"
            rf"\def\studentserial{{{ssn}}}"
        )
        _run_pdflatex(workdir, source_filename, jobname=jobname, pre_input=pre_input)
        _cleanup_aux(workdir, jobname)

        student_pdfs.append(out_pdf)
        register_rows.append({
            "name": name,
            "canonical_name": canonical_name(name),
            "source_serial": src_serial,
            "student_serial": ssn,
            "output_pdf": out_pdf.name,
        })

    # Write register CSV
    register_path = cfg.register_out if cfg.register_out else workdir / f"{stem}_serials.csv"
    with register_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["name", "canonical_name", "source_serial", "student_serial", "output_pdf"],
        )
        writer.writeheader()
        writer.writerows(register_rows)

    combined_pdf: Path | None = None
    if cfg.combined:
        # Sort by canonical name for the combined print stack
        sorted_pairs = sorted(
            zip(register_rows, student_pdfs),
            key=lambda pair: pair[0]["canonical_name"],
        )
        sorted_pdfs = [pdf for _, pdf in sorted_pairs]
        combined_pdf = workdir / f"{stem}_combined.pdf"
        combined_pdf.unlink(missing_ok=True)
        _concat_pdfs(sorted_pdfs, combined_pdf)

    return BuildResult(
        source_serial=src_serial,
        student_pdfs=student_pdfs,
        key_pdf=key_pdf,
        register_csv=register_path,
        combined_pdf=combined_pdf,
    )


# ----- CLI -----------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pa-exam-build",
        description="Compile a single-source exam .tex into student + key PDFs.",
    )
    p.add_argument("source", type=Path, help="path to exam .tex")
    p.add_argument(
        "--roster",
        type=Path,
        default=None,
        help="roster CSV (must have a 'name' column); switches to per-student mode",
    )
    p.add_argument(
        "--combined",
        action="store_true",
        help="(with --roster) also produce <stem>_combined.pdf sorted by canonical name",
    )
    p.add_argument(
        "--register",
        type=Path,
        default=None,
        help="(with --roster) write register CSV here (default: <stem>_serials.csv next to source)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.source.suffix.lower() in (".yaml", ".yml"):
        from lectern import exam_pack
        if args.roster or args.combined or args.register:
            parser.error("--roster/--combined/--register are not valid with a .yaml manifest "
                         "(configure them in the manifest instead)")
        manifest = exam_pack.load_manifest(args.source)
        result = exam_pack.run(manifest, args.source.parent)
        print(f"  forms: {', '.join(result.forms)}")
        print(f"  + build/  ({result.student_pdf_count} student PDF(s))")
        if result.register_csv:
            base = args.source.resolve().parent
            try:
                shown = result.register_csv.relative_to(base)
            except ValueError:
                shown = result.register_csv
            print(f"  + {shown}")
        if result.gradescope_dir:
            print(f"  + gradescope/  ({manifest.gradescope})")
        return 0

    if args.combined and args.roster is None:
        parser.error("--combined requires --roster")
    if args.register is not None and args.roster is None:
        parser.error("--register requires --roster")

    cfg = ExamBuildConfig(
        source=args.source,
        roster=args.roster,
        combined=args.combined,
        register_out=args.register,
    )

    if cfg.roster is None:
        result = build_variant(cfg)
        print(f"  source serial: {result.source_serial}")
        print(f"  + {result.student_pdfs[0].name}")
        print(f"  + {result.key_pdf.name}")
    else:
        result = build_roster(cfg)
        print(f"  source serial: {result.source_serial}")
        print(f"  + {len(result.student_pdfs)} student PDF(s)")
        print(f"  + {result.key_pdf.name}")
        print(f"  + {result.register_csv.name}")
        if result.combined_pdf is not None:
            print(f"  + {result.combined_pdf.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""reg-syllabus — stamp a syllabus repo with its control-number serial and build
the distribution HTML. See the syllabus design spec + [[notes/syllabus-doctrine]]."""
from __future__ import annotations
import argparse
import re
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from lectern.syllabus_serial import compute_serial, primary_md

_FM_BLOCK = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_FOOTER_RE = re.compile(r"(?m)^\*Syllabus version [0-9A-F]{8} · [0-9-]+\*\s*$\n?")
_REPO_NAME = re.compile(r"cecs-(?P<course>\d+)-(?P<term>[a-z]{2}\d{2})-(?P<section>\d+)-syllabus-(?P<crn>\w+)")

_CSS = Path(__file__).parent / "references" / "syllabus.css"
_EISVOGEL = Path(__file__).parent / "references" / "eisvogel.latex"

_REG_HEADER = ("\n## Live (Su26 forward)\n\n"
               "| Course | Section | Term | CRN | Serial | Date | Revision-of |\n"
               "| --- | --- | --- | --- | --- | --- | --- |\n")


def _set_frontmatter(text: str, serial: str, revision_of: str | None) -> str:
    m = _FM_BLOCK.match(text)
    body_fm = m.group(1) if m else ""
    lines = [ln for ln in body_fm.splitlines()
             if not ln.startswith(("serial:", "revision-of:"))]
    lines.append(f"serial: {serial}")
    if revision_of:
        lines.append(f"revision-of: {revision_of}")
    new_fm = "---\n" + "\n".join(lines).strip("\n") + "\n---\n"
    return new_fm + (text[m.end():] if m else text)


def _set_footer(text: str, serial: str, today: str) -> str:
    text = _FOOTER_RE.sub("", text).rstrip("\n")
    return text + f"\n\n*Syllabus version {serial} · {today}*\n"


def _append_register(vault_root: Path, repo: Path, serial: str,
                     today: str, revision_of: str | None) -> None:
    reg = vault_root / "notes" / "syllabus-serial-register.md"
    text = reg.read_text(encoding="utf-8") if reg.exists() else "# Syllabus Serial Register\n"
    if f"| {serial} |" in text:
        return                                   # idempotent on serial
    if "## Live (Su26 forward)" not in text:
        text = text.rstrip("\n") + "\n" + _REG_HEADER
    m = _REPO_NAME.search(repo.name)
    c = m.groupdict() if m else {"course": "?", "term": "?", "section": "?", "crn": "?"}
    row = (f"| {c['course']} | {c['section']} | {c['term']} | {c['crn']} "
           f"| {serial} | {today} | {revision_of or ''} |\n")
    reg.write_text(text.rstrip("\n") + "\n" + row, encoding="utf-8")


def stamp(repo, vault_root, revision_of: str | None = None, today: str | None = None) -> str:
    repo = Path(repo)
    today = today or date.today().isoformat()
    serial = compute_serial(repo)
    pm = repo / primary_md(repo)
    text = pm.read_text(encoding="utf-8")
    text = _set_frontmatter(text, serial, revision_of)
    text = _set_footer(text, serial, today)
    pm.write_text(text, encoding="utf-8")
    _append_register(Path(vault_root), repo, serial, today, revision_of)
    return serial


def _read_serial(pm: Path) -> str:
    m = re.search(r"(?m)^serial:\s*(\S+)", pm.read_text(encoding="utf-8"))
    return m.group(1) if m else ""


def _write_tmp(content: str) -> str:
    """Write content to a NamedTemporaryFile and return its path string."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(content)
        return f.name


def _build_canvas(pm: Path, out: Path, serial: str) -> None:
    """Render a Canvas-RCE-safe inline-styled HTML fragment from the primary md.

    Ported verbatim from ~/git/cecs-378-su26-01-syllabus-10660/gen_canvas.py.
    Canvas strips <head>, <style>, <script>, @font-face, and class= attributes,
    but keeps inline style= on elements. We pandoc the md to an HTML fragment,
    then inject inline styles on structural elements and flatten Canvas-unsafe
    constructs (frontmatter, comments, anchor nav, <details>).
    """
    INK, ACCENT, MUTED, HAIR, PANEL = "#14130f", "#b22f12", "#6c675d", "#ddd8cb", "#f2efe6"
    SANS = "'Helvetica Neue',Helvetica,Arial,sans-serif"
    MONO = "'Courier New',monospace"

    md = pm.read_text(encoding="utf-8")

    # extract serial from YAML frontmatter before stripping
    serial_match = re.search(r"^serial:\s*(\S+)", md, re.MULTILINE)
    SERIAL = serial_match.group(1) if serial_match else serial

    # strip YAML frontmatter
    md = re.sub(r"\A---\n.*?\n---\n", "", md, count=1, flags=re.DOTALL)
    # strip HTML comments (template banner, term-var markers)
    md = re.sub(r"<!--.*?-->", "", md, flags=re.DOTALL)
    # drop the "Jump to:" anchor-nav paragraph (Canvas heading ids differ)
    md = re.sub(r"\*\*Jump to:\*\*.*?(?=\n##\s)", "", md, flags=re.DOTALL)
    # flatten the <details> resources block → plain heading (Canvas support is spotty)
    md = md.replace("<details>", "").replace("</details>", "")
    md = re.sub(r"<summary>.*?</summary>", "", md, flags=re.DOTALL)

    frag = subprocess.run(
        ["pandoc", "--from", "gfm", "--to", "html5"],
        input=md, capture_output=True, text=True, check=True,
    ).stdout

    # h1
    frag = re.sub(
        r"<h1[^>]*>(.*?)</h1>",
        rf'<h1 style="font-family:{SANS};font-size:2em;font-weight:800;color:{INK};'
        rf'border-top:5px solid {INK};padding-top:0.5em;margin:0 0 0.3em;letter-spacing:-0.02em;">\1</h1>',
        frag, flags=re.DOTALL,
    )
    # numbered h2 banners
    _n = [0]
    def _h2(m):
        _n[0] += 1
        return (f'<h2 style="font-family:{SANS};font-size:1.4em;font-weight:700;color:{INK};'
                f'border-top:2px solid {INK};padding-top:0.45em;margin:1.8em 0 0.7em;letter-spacing:-0.01em;">'
                f'<span style="font-family:{MONO};color:{ACCENT};font-size:0.7em;">{_n[0]:02d} / </span>{m.group(1)}</h2>')
    frag = re.sub(r"<h2[^>]*>(.*?)</h2>", _h2, frag, flags=re.DOTALL)
    # h3
    frag = re.sub(
        r"<h3[^>]*>(.*?)</h3>",
        rf'<h3 style="font-family:{SANS};font-size:1.08em;font-weight:600;color:{INK};margin:1.3em 0 0.4em;">'
        rf'<span style="color:{ACCENT};">▪</span> \1</h3>',
        frag, flags=re.DOTALL,
    )
    # tables
    frag = frag.replace("<table>", f'<table style="width:100%;border-collapse:collapse;margin:1em 0;font-family:{SANS};">')
    frag = frag.replace("<th ", f'<th data-x ').replace("<th>", "<th>")
    frag = re.sub(r"<th[^>]*>(.*?)</th>",
                  rf'<th style="text-align:left;padding:6px 10px;border-bottom:2px solid {INK};'
                  rf'font-family:{MONO};font-size:0.8em;text-transform:uppercase;color:{MUTED};">\1</th>',
                  frag, flags=re.DOTALL)
    frag = re.sub(r"<td[^>]*>(.*?)</td>",
                  rf'<td style="padding:6px 10px;border-bottom:1px solid {HAIR};vertical-align:top;">\1</td>',
                  frag, flags=re.DOTALL)
    # blockquote (subtitle + any stray)
    frag = frag.replace("<blockquote>",
                        f'<blockquote style="border-left:3px solid {ACCENT};margin:0.6em 0;padding:0.2em 0 0.2em 0.9em;color:{MUTED};font-family:{MONO};">')
    # GitHub-alert divs → bordered callouts
    ALERT = {"note": "#3b6ea5", "tip": "#2e7d4f", "important": ACCENT, "warning": "#a8740f", "caution": "#a5281c"}
    for kind, col in ALERT.items():
        frag = frag.replace(
            f'<div class="{kind}">',
            f'<div style="border-left:4px solid {col};background:{PANEL};padding:0.7em 1em;margin:1.1em 0;">')
    frag = re.sub(r'<div class="title">\s*<p>(.*?)</p>\s*</div>',
                  rf'<p style="font-family:{MONO};font-size:0.78em;text-transform:uppercase;letter-spacing:0.08em;'
                  rf'font-weight:700;margin:0 0 0.3em;">\1</p>', frag, flags=re.DOTALL)

    # serial footer (Canvas-safe inline styles; entity-escaped · to avoid charset issues)
    serial_footer = (
        f'<footer style="margin-top:2rem;padding-top:0.7rem;border-top:1px solid #ddd8cb;'
        f'font-family:\'Courier New\',monospace;font-size:0.62rem;letter-spacing:0.18em;'
        f'text-transform:uppercase;color:#6c675d;text-align:right;">'
        f'Serial · {SERIAL}</footer>'
    ) if SERIAL else ""

    wrapper = (f'<div style="font-family:{SANS};color:{INK};line-height:1.55;max-width:52rem;">\n'
               f'{frag}\n'
               f'{serial_footer}\n'
               f'</div>\n')
    out.write_text(wrapper, encoding="utf-8")


def _build_pdf(repo: Path, html: Path) -> Path:
    pdf = html.with_suffix(".pdf")
    import shutil
    if shutil.which("weasyprint"):
        subprocess.run(["weasyprint", str(html), str(pdf)], check=True)
        return pdf
    if shutil.which("chromium"):
        subprocess.run(["chromium", "--headless", f"--print-to-pdf={pdf}", str(html)], check=True)
        return pdf
    raise SystemExit("syllabus: no weasyprint/chromium for --pdf; print the HTML")


def build(repo, pdf: bool = False) -> list[Path]:
    repo = Path(repo)
    pm = repo / primary_md(repo)
    serial = _read_serial(pm)
    html = repo / "syllabus.html"
    footer = f'<footer class="serial">Serial · {serial or "—"}</footer>'
    subprocess.run(
        ["pandoc", str(pm), "--from", "gfm", "--to", "html5", "--standalone",
         "--embed-resources", "--css", str(_CSS),
         "--metadata", "lang=en", f"--include-after-body={_write_tmp(footer)}",
         "-o", str(html)], check=True)
    canvas = repo / "syllabus_canvas.html"
    _build_canvas(pm, canvas, serial)
    out = [html, canvas]
    if pdf:
        out.append(_build_pdf(repo, html))
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="reg-syllabus", description="Syllabus stamp + build.")
    sub = p.add_subparsers(dest="cmd", required=True)
    ps = sub.add_parser("stamp", help="Compute + inject the control-number serial; append register row.")
    ps.add_argument("repo", type=Path)
    ps.add_argument("--vault-root", type=Path, required=True)
    ps.add_argument("--revision-of", default=None)
    ps.add_argument("--date", default=None)
    pb = sub.add_parser("build", help="Render HTML + Canvas variant (PDF opt-in).")
    pb.add_argument("repo", type=Path)
    pb.add_argument("--pdf", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "stamp":
        s = stamp(a.repo, a.vault_root, revision_of=a.revision_of, today=a.date)
        print(f"stamped {a.repo.name}: serial {s}")
    else:
        outs = build(a.repo, pdf=a.pdf)
        print("built: " + ", ".join(o.name for o in outs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

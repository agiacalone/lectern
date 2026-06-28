"""Extract structured fields + raw text from a student doc. No summarization."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re, yaml

@dataclass
class DocRecon:
    label: str
    present: bool = False
    frontmatter: dict = field(default_factory=dict)
    sections: list[str] = field(default_factory=list)
    sources: int = 0
    word_count: int = 0
    raw_path: str = ""
    body: str = ""

_FM = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def resolve_doc_path(repo_root: Path, rel_file: str) -> Path:
    """Resolve a manifest deliverable path tolerantly within a repo.

    Students name the writeup inconsistently — ``WRITEUP.md``, ``Writeup.md``,
    ``submission/writeup.md``, ``CECS 378 Lab Writeup.md``. The strict
    ``repo/<rel_file>`` check marked all of those not-present (a false doc-✗) and
    dropped them from the writeup snapshot. Resolve in priority order:

      1. exact ``repo/<rel_file>``
      2. case-insensitive basename match anywhere in the tree (shallowest wins)
      3. a *single* ``.md`` whose name contains the configured stem (e.g. ``…Writeup.md``)

    Ambiguous (2+ fuzzy candidates) or not-found returns the canonical path, so
    the caller records ``present=False`` exactly as before. ``.git`` is never searched.
    """
    repo_root = Path(repo_root)
    canonical = repo_root / rel_file
    if canonical.exists():
        return canonical
    target = Path(rel_file).name.lower()
    stem = Path(rel_file).stem.lower()
    files = [p for p in repo_root.rglob("*")
             if p.is_file() and ".git" not in p.relative_to(repo_root).parts]
    ci = sorted((p for p in files if p.name.lower() == target),
                key=lambda p: len(p.relative_to(repo_root).parts))
    if ci:
        return ci[0]
    fuzzy = [p for p in files if p.suffix.lower() == ".md" and stem in p.name.lower()]
    if len(fuzzy) == 1:
        return fuzzy[0]
    return canonical

def recon_doc(path: Path, *, label: str) -> DocRecon:
    p = Path(path)
    if not p.exists():
        return DocRecon(label=label, present=False)
    text = p.read_text(encoding="utf-8", errors="replace")
    fm: dict = {}
    m = _FM.match(text)
    body = text
    if m:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            fm = {}
        body = text[m.end():]
    sections = re.findall(r"^#{1,6}\s+(.*)$", body, re.MULTILINE)
    src = fm.get("sources")
    sources = len(src) if isinstance(src, list) else len(re.findall(r"https?://", body))
    return DocRecon(label=label, present=True, frontmatter=fm if isinstance(fm, dict) else {},
                    sections=[s.strip() for s in sections], sources=sources,
                    word_count=len(body.split()), raw_path=str(p), body=body.strip())

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

_FM = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

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
                    word_count=len(body.split()), raw_path=str(p))

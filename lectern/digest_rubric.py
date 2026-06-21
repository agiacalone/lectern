"""Parse + validate a lab digest rubric YAML into a Rubric (deterministic)."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import sys
import yaml

@dataclass
class Section:
    key: str; label: str; max: int
    anchors: dict = field(default_factory=dict)
    requires_cleared: str | None = None

@dataclass
class Rubric:
    lab: str; total: int; comment_max_chars: int
    sections: list[Section]; bonus: list[Section]; cap: int

def _section(d: dict) -> Section:
    for _k in ("key", "max"):
        if _k not in d:
            sys.exit(f"digest_rubric: section missing required key '{_k}': {d!r}")
    return Section(key=str(d["key"]), label=str(d.get("label", d["key"])),
                   max=int(d["max"]), anchors=dict(d.get("anchors") or {}),
                   requires_cleared=(str(d["requires_cleared"]) if d.get("requires_cleared") else None))

def load_rubric(path: Path) -> Rubric:
    data = yaml.safe_load(Path(path).read_text()) or {}
    for k in ("lab", "total", "sections"):
        if k not in data:
            sys.exit(f"digest_rubric: missing required key '{k}'")
    sections = [_section(s) for s in data["sections"]]
    bonus = [_section(s) for s in (data.get("bonus") or [])]
    total = int(data["total"])
    cap = int(data.get("cap", total))
    keys = [s.key for s in sections + bonus]
    if len(keys) != len(set(keys)):
        sys.exit("digest_rubric: duplicate section keys")
    for s in sections + bonus:
        if s.max < 0:
            sys.exit(f"digest_rubric: negative max on '{s.key}'")
    if sum(s.max for s in sections) != total:
        sys.exit(f"digest_rubric: core section maxes ({sum(s.max for s in sections)}) != total ({total})")
    if cap < total:
        sys.exit("digest_rubric: cap must be >= total")
    return Rubric(lab=str(data["lab"]), total=total,
                  comment_max_chars=int(data.get("comment_max_chars", 140)),
                  sections=sections, bonus=bonus, cap=cap)

"""emit: recon bundle + rubric -> digest_tasks.jsonl + digest.schema.json (deterministic)."""
from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
from lectern.digest_rubric import Rubric
from lectern.digest_schema import result_schema

def _rubric_dict(r: Rubric) -> dict:
    return {"lab": r.lab, "total": r.total, "comment_max_chars": r.comment_max_chars, "cap": r.cap,
            "sections": [asdict(s) for s in r.sections], "bonus": [asdict(s) for s in r.bonus]}

def emit(bundle_dir: Path, rubric: Rubric, out_tasks: Path) -> int:
    bundle_dir = Path(bundle_dir)
    schema = result_schema(rubric)
    (out_tasks.parent).mkdir(parents=True, exist_ok=True)
    (out_tasks.parent / "digest.schema.json").write_text(json.dumps(schema, indent=2, sort_keys=True))
    rd = _rubric_dict(rubric)
    n = 0
    lines = []
    for jf in sorted((bundle_dir / "repos").glob("*.json")):
        rec = json.loads(jf.read_text())
        gid = rec["github_id"]
        ag = rec.get("autograde") or {}
        honor_ok = bool(ag.get("honor_ok"))
        cleared = sorted(k for k, c in (ag.get("challenges") or {}).items() if c.get("passed"))
        wpath = bundle_dir / "writeups" / f"{gid}.md"
        body = wpath.read_text(encoding="utf-8") if wpath.exists() else ""
        skip = (not honor_ok) or (not body.strip())
        task = {"github_id": gid, "student": rec.get("student", gid),
                "writeup_text": body, "skip": skip,
                "autograde": {"points": int(ag.get("points", 0)), "cleared": cleared, "honor_ok": honor_ok},
                "rubric": rd, "schema": schema}
        lines.append(json.dumps(task, sort_keys=True))
        if not skip:
            n += 1
    out_tasks.write_text("\n".join(lines) + ("\n" if lines else ""))
    return n

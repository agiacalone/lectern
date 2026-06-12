"""qbank — question-bank model, parser, validator, and CLI.

Parses YAML-in-fenced-block question records from a Markdown topic note and
builds a canonical ``{id: Question}`` bank.  Downstream consumers — exam
assembly and the grading-note emitter — read the bank, never re-author.

Usage (CLI)::

    reg-qbank validate <file.md>
    reg-qbank emit <file.md> --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

_VALID_TYPES = {"mc", "tf", "fib", "code"}

# Regex: fenced ```yaml ... ``` blocks (non-greedy, DOTALL)
_FENCE_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)


@dataclass
class Outcome:
    key: str
    text: str = ""
    credited: bool = False
    feedback: str = ""
    accept: list[str] = field(default_factory=list)
    points: float = 0.0


@dataclass
class Question:
    id: str
    topic: str
    type: str
    points: float
    stem: str
    outcomes: list[Outcome]
    section: str = ""
    difficulty: int = 1
    bloom: str = ""
    exam_eligible: bool = True
    tags: list[str] = field(default_factory=list)
    citation: str = ""

    # --- helpers ---

    @property
    def credited_outcome(self) -> Outcome:
        for o in self.outcomes:
            if o.credited:
                return o
        raise ValueError(f"qbank: {self.id}: no credited outcome found")

    def outcome(self, key: str) -> Outcome:
        for o in self.outcomes:
            if o.key == key:
                return o
        raise KeyError(f"qbank: {self.id}: outcome key '{key}' not found")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_outcome(raw: dict[str, Any], default_points: float, credited_points: float) -> Outcome:
    """Build an Outcome from a raw dict, deriving per-outcome points."""
    credited = bool(raw.get("credited", False))
    pts_raw = raw.get("points")
    if pts_raw is not None:
        pts = float(pts_raw)
    else:
        pts = credited_points if credited else 0.0
    return Outcome(
        key=str(raw.get("key", "")),
        text=str(raw.get("text", "")),
        credited=credited,
        feedback=str(raw.get("feedback", "")),
        accept=list(raw.get("accept", [])),
        points=pts,
    )


def _scaffold_outcomes(record: dict[str, Any]) -> list[Outcome]:
    """Build outcomes from thin authoring (options+answer / answer T/F / fib blanks).

    Called only when ``outcomes`` is absent in the record.
    """
    qtype = str(record.get("type", "mc")).lower()
    points = float(record.get("points", 1))
    answer_raw = str(record.get("answer", "")).strip()

    if qtype == "mc":
        options: dict[str, str] = record.get("options", {}) or {}
        answer_key = answer_raw.lower()
        outcomes = []
        for k, v in options.items():
            k_lower = k.lower()
            credited = (k_lower == answer_key)
            outcomes.append(Outcome(
                key=k_lower,
                text=str(v),
                credited=credited,
                feedback="",
                points=points if credited else 0.0,
            ))
        outcomes.append(Outcome(key="none", text="No answer / multiple marks",
                                credited=False, feedback="", points=0.0))
        return outcomes

    if qtype in ("tf", "code"):
        answer_key = answer_raw.lower()
        outcomes = []
        for k in ("true", "false"):
            credited = (k == answer_key)
            outcomes.append(Outcome(
                key=k,
                text=k.capitalize(),
                credited=credited,
                feedback="",
                points=points if credited else 0.0,
            ))
        outcomes.append(Outcome(key="none", text="No answer / multiple marks",
                                credited=False, feedback="", points=0.0))
        return outcomes

    if qtype == "fib":
        # fib: answer is a list of blanks; accept is a parallel list of lists
        answers = record.get("answer", [])
        if isinstance(answers, str):
            answers = [answers]
        accepts = record.get("accept", [])
        if isinstance(accepts, list) and accepts and not isinstance(accepts[0], list):
            accepts = [[a] for a in accepts]
        n = len(answers)
        if n == 0:
            return []
        pts_per = points / n
        outcomes = []
        for i, ans in enumerate(answers):
            blank_key = f"b{i + 1}"
            acc = accepts[i] if i < len(accepts) else [str(ans)]
            outcomes.append(Outcome(
                key=blank_key,
                text=str(ans),
                credited=True,
                feedback="",
                accept=acc,
                points=pts_per,
            ))
            outcomes.append(Outcome(
                key=f"{blank_key}-miss",
                text="",
                credited=False,
                feedback="",
                points=0.0,
            ))
        return outcomes

    return []


def _build_question(record: dict[str, Any]) -> Question:
    """Convert a raw parsed YAML dict to a Question."""
    qid = str(record.get("id", "")).strip()
    qtype = str(record.get("type", "")).strip().lower()
    points = float(record.get("points", 1))

    raw_outcomes = record.get("outcomes")
    if raw_outcomes:
        # Determine credited_points for fib (split evenly unless per-outcome given)
        credited_count = sum(1 for o in raw_outcomes if o.get("credited", False))
        if qtype == "fib" and credited_count > 0:
            credited_pts = points / credited_count
        else:
            credited_pts = points
        outcomes = [_parse_outcome(o, points, credited_pts) for o in raw_outcomes]
    else:
        outcomes = _scaffold_outcomes(record)

    return Question(
        id=qid,
        topic=str(record.get("topic", "")),
        type=qtype,
        points=points,
        stem=str(record.get("stem", "")),
        outcomes=outcomes,
        section=str(record.get("section", "")),
        difficulty=int(record.get("difficulty", 1)),
        bloom=str(record.get("bloom", "")),
        exam_eligible=bool(record.get("exam-eligible", True)),
        tags=list(record.get("tags", [])),
        citation=str(record.get("citation", "")),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_bank(path) -> dict[str, Question]:
    """Parse all ```yaml fenced blocks in *path* and return ``{id: Question}``."""
    from pathlib import Path as _Path
    text = _Path(path).read_text(encoding="utf-8")
    bank: dict[str, Question] = {}
    for match in _FENCE_RE.finditer(text):
        record = yaml.safe_load(match.group(1))
        if not isinstance(record, dict) or "id" not in record:
            continue
        q = _build_question(record)
        # For duplicate detection we keep the first and let validate() catch extras.
        if q.id not in bank:
            bank[q.id] = q
        else:
            # Store under a sentinel that validate() will detect as a duplicate.
            bank[f"__dup__{q.id}"] = q
    return bank


def validate(bank: dict[str, Question]) -> None:
    """Validate the bank, raising ``SystemExit("qbank: <id>: <reason>")`` on any error.

    Rules:
    - Unique IDs (no ``__dup__`` sentinels).
    - ``type`` in the allowed set.
    - ``points`` > 0.
    - mc/tf/code: exactly one credited outcome; a ``none`` outcome present.
    - fib: each credited blank has a non-empty ``accept`` list; no ``none`` required.
    """
    for key, q in bank.items():
        if key.startswith("__dup__"):
            real_id = key[len("__dup__"):]
            raise SystemExit(f"qbank: {real_id}: duplicate id")

    for q in bank.values():
        if q.type not in _VALID_TYPES:
            raise SystemExit(f"qbank: {q.id}: invalid type '{q.type}'")
        if q.points <= 0:
            raise SystemExit(f"qbank: {q.id}: points must be > 0")

        if q.type == "fib":
            for o in q.outcomes:
                if o.credited and not o.accept:
                    raise SystemExit(f"qbank: {q.id}: fib accept-list required for blank '{o.key}'")
        else:
            credited = [o for o in q.outcomes if o.credited]
            if len(credited) != 1:
                raise SystemExit(
                    f"qbank: {q.id}: exactly one credited outcome required "
                    f"(found {len(credited)})"
                )
            keys = {o.key for o in q.outcomes}
            if "none" not in keys:
                raise SystemExit(f"qbank: {q.id}: missing 'none' outcome")


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _bank_to_dict(bank: dict[str, Question]) -> dict[str, Any]:
    """Convert bank to a JSON-serializable dict with stable key order."""
    out: dict[str, Any] = {}
    for qid in sorted(bank.keys()):
        q = bank[qid]
        out[qid] = {
            "id": q.id,
            "topic": q.topic,
            "type": q.type,
            "points": q.points,
            "section": q.section,
            "difficulty": q.difficulty,
            "bloom": q.bloom,
            "exam_eligible": q.exam_eligible,
            "tags": q.tags,
            "stem": q.stem,
            "outcomes": [
                {
                    "key": o.key,
                    "text": o.text,
                    "credited": o.credited,
                    "feedback": o.feedback,
                    "accept": o.accept,
                    "points": o.points,
                }
                for o in q.outcomes
            ],
            "citation": q.citation,
        }
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="reg-qbank",
        description="Question-bank validator and emitter.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="Validate a question-bank Markdown file.")
    p_val.add_argument("file", help="Path to the Markdown file containing ```yaml records.")

    p_emit = sub.add_parser("emit", help="Emit the canonical bank.")
    p_emit.add_argument("file", help="Path to the Markdown file.")
    p_emit.add_argument("--json", action="store_true", help="Emit as JSON.")

    args = parser.parse_args(argv)

    if args.cmd == "validate":
        bank = load_bank(args.file)
        validate(bank)
        print(f"OK — {len(bank)} question(s) valid.")

    elif args.cmd == "emit":
        bank = load_bank(args.file)
        validate(bank)
        if args.json:
            print(json.dumps(_bank_to_dict(bank), indent=2, ensure_ascii=False))
        else:
            for qid, q in sorted(bank.items()):
                print(f"{qid}: {q.stem[:60]}")


if __name__ == "__main__":
    main()

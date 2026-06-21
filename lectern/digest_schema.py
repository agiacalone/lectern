"""Output contract for one digest result + a non-raising validator."""
from __future__ import annotations
from jsonschema import Draft202012Validator
from lectern.digest_rubric import Rubric

def result_schema(rubric: Rubric) -> dict:
    sec_keys = [s.key for s in rubric.sections]
    bonus_keys = [s.key for s in rubric.bonus]
    return {
        "type": "object",
        "required": ["github_id", "sections", "total", "comment", "confidence", "abstain"],
        "additionalProperties": False,
        "properties": {
            "github_id": {"type": "string", "minLength": 1},
            "sections": {"type": "object", "required": sec_keys, "additionalProperties": False,
                         "properties": {k: {"type": "integer", "minimum": 0} for k in sec_keys}},
            "bonus": {"type": "object", "additionalProperties": False,
                      "properties": {k: {"type": "integer", "minimum": 0} for k in bonus_keys}},
            "total": {"type": "integer", "minimum": 0},
            "comment": {"type": "string"},
            "confidence": {"enum": ["high", "medium", "low"]},
            "abstain": {"type": "boolean"},
        },
    }

def validate_result(obj: dict, rubric: Rubric) -> list[str]:
    v = Draft202012Validator(result_schema(rubric))
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
            for e in sorted(v.iter_errors(obj), key=lambda e: list(e.path))]

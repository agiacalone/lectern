"""Tests for lectern.qbank — question-bank model, parser, validator, CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

VENV_PYTHON = "/home/anthony/.local/share/personal-assistant/venv/bin/python"
FIXTURE_DIR = Path("tests/fixtures/qbank")


# ---------------------------------------------------------------------------
# Task 1: canonical model + load one record
# ---------------------------------------------------------------------------

def test_load_one_mc():
    from lectern.qbank import load_bank, Question, Outcome
    bank = load_bank(FIXTURE_DIR / "one_mc.md")
    q = bank["mal-m01"]
    assert q.type == "mc" and q.points == 2
    assert sum(o.credited for o in q.outcomes) == 1
    assert {o.key for o in q.outcomes} == {"a", "b", "c", "d", "none"}
    assert q.credited_outcome.key == "b"
    assert q.outcome("a").feedback.startswith("Reversed")


# ---------------------------------------------------------------------------
# Task 2: validation rules
# ---------------------------------------------------------------------------

def test_validate_two_credited_raises():
    from lectern.qbank import load_bank, validate
    bank = load_bank(FIXTURE_DIR / "bad_two_credited.md")
    with pytest.raises(SystemExit, match="exactly one credited"):
        validate(bank)


def test_validate_missing_none_raises():
    from lectern.qbank import load_bank, validate
    bank = load_bank(FIXTURE_DIR / "bad_missing_none.md")
    with pytest.raises(SystemExit, match="missing 'none' outcome"):
        validate(bank)


def test_validate_fib_empty_accept_raises():
    from lectern.qbank import load_bank, validate
    bank = load_bank(FIXTURE_DIR / "bad_fib_empty_accept.md")
    with pytest.raises(SystemExit, match="fib accept-list required"):
        validate(bank)


def test_validate_duplicate_id_raises():
    from lectern.qbank import load_bank, validate
    bank = load_bank(FIXTURE_DIR / "bad_duplicate_id.md")
    with pytest.raises(SystemExit, match="duplicate id"):
        validate(bank)


def test_validate_clean_bank_passes():
    from lectern.qbank import load_bank, validate
    bank = load_bank(FIXTURE_DIR / "one_mc.md")
    validate(bank)  # should not raise


# ---------------------------------------------------------------------------
# Task 3: outcome scaffolding for thin authoring
# ---------------------------------------------------------------------------

def test_scaffold_thin_mc():
    from lectern.qbank import load_bank
    bank = load_bank(FIXTURE_DIR / "thin_mc.md")
    q = bank["thin-m01"]
    assert len(q.outcomes) == 5
    keys = {o.key for o in q.outcomes}
    assert keys == {"a", "b", "c", "d", "none"}
    assert q.credited_outcome.key == "b"
    # distractors have empty feedback (not yet authored)
    for o in q.outcomes:
        if o.key not in ("b", "none"):
            assert o.feedback == ""


# ---------------------------------------------------------------------------
# Task 4: CLI — validate / emit --json
# ---------------------------------------------------------------------------

def test_cli_validate_clean_exits_0():
    result = subprocess.run(
        [VENV_PYTHON, "-m", "lectern.qbank", "validate",
         str(FIXTURE_DIR / "one_mc.md")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_cli_validate_malformed_exits_nonzero():
    result = subprocess.run(
        [VENV_PYTHON, "-m", "lectern.qbank", "validate",
         str(FIXTURE_DIR / "bad_two_credited.md")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "exactly one credited" in result.stderr or "exactly one credited" in result.stdout


def test_cli_emit_json():
    result = subprocess.run(
        [VENV_PYTHON, "-m", "lectern.qbank", "emit",
         str(FIXTURE_DIR / "one_mc.md"), "--json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "mal-m01" in data
    assert data["mal-m01"]["type"] == "mc"

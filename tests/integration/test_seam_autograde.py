# tests/integration/test_seam_autograde.py
"""Seam B (golden): Oracle result.json -> Lectern AutogradeResult contract."""
import json
import pytest
from lectern.recon_autograde import parse_result_json

pytestmark = pytest.mark.suite


def test_allpass_contract(fixtures_dir):
    r = parse_result_json((fixtures_dir / "autograde/result_allpass.json").read_text())
    assert r is not None
    assert r.honor_ok is True
    assert r.points == 60 and r.max == 60
    assert set(r.challenges) == {"ward1", "ward2", "ward3"}
    assert r.challenges["ward2"].passed is True
    assert r.commit == "a11pa55"


def test_partial_zeroes_failed_ward(fixtures_dir):
    r = parse_result_json((fixtures_dir / "autograde/result_partial.json").read_text())
    assert r.points == 25
    assert r.challenges["ward2"].passed is False
    assert r.challenges["ward2"].points == 0


def test_honor_gate_surfaced(fixtures_dir):
    r = parse_result_json((fixtures_dir / "autograde/result_honorfail.json").read_text())
    assert r.honor_ok is False


def test_malformed_json_returns_none():
    assert parse_result_json("{not json") is None

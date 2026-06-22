"""Seam C: Lectern bank round-trips; Scriptorium bank does NOT parse (known gap)."""
import pytest
from lectern.qbank import load_bank, validate

pytestmark = pytest.mark.suite


def test_lectern_bank_loads_and_validates(fixtures_dir):
    bank = load_bank(fixtures_dir / "qbank/lectern_bank.md")
    validate(bank)                       # raises on any contract violation
    assert set(bank) == {"m01", "t01"}
    assert bank["m01"].type == "mc"
    assert any(o.credited for o in bank["m01"].outcomes)


@pytest.mark.xfail(strict=True,
                   reason="KNOWN GAP: Scriptorium markdown-monolith bank is not parseable "
                          "by lectern.qbank (expects YAML-fenced). Closing the gap flips this.")
def test_scriptorium_bank_is_not_yet_consumable(fixtures_dir):
    bank = load_bank(fixtures_dir / "qbank/scriptorium_bank.md")
    # If an adapter ever lands, this assert starts passing and the strict xfail fails loudly,
    # forcing this test to be updated to the new contract.
    assert bank and all(q.outcomes for q in bank.values())

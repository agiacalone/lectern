import pytest
from lectern.lab_report import main


def test_requires_subcommand():
    with pytest.raises(SystemExit):
        main([])


def test_render_dispatch(monkeypatch):
    called = {}
    monkeypatch.setattr("lectern.report_render.main",
                        lambda argv: called.update(render=argv) or 0)
    assert main(["render", "--bundle", "b", "--cohort", "c", "--manifest", "m", "--out", "o"]) == 0
    assert called["render"][0] == "--bundle"


def test_deliver_dispatch(monkeypatch):
    called = {}
    monkeypatch.setattr("lectern.feedback_deliver.main",
                        lambda argv: called.update(deliver=argv) or 0)
    assert main(["deliver", "--cohort", "c", "--manifest", "m"]) == 0
    assert "deliver" in called

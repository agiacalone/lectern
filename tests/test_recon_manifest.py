from pathlib import Path
from lectern.recon_manifest import load_manifest, ReconManifest

FIX = Path(__file__).parent / "fixtures" / "recon" / "spellbreaker.recon.yaml"

def test_load_manifest_parses_core_fields():
    m = load_manifest(FIX)
    assert isinstance(m, ReconManifest)
    assert m.org == "Giacalone-CECS"
    assert m.repo_prefix == "cecs-378-su26-01-lab-01-symmetric-crypto-"
    assert m.total_points == 100
    assert m.autograde.result_path == "grading/result.json"
    assert m.docs[0].label == "grimoire"
    assert m.docs[0].points == 30

def test_load_manifest_missing_required_raises():
    import pytest, yaml, tempfile
    bad = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    yaml.safe_dump({"assignment": {"course": "X"}}, bad); bad.close()
    with pytest.raises(ValueError, match="repo_prefix"):
        load_manifest(Path(bad.name))

def test_autograde_optional():
    import yaml, tempfile
    data = {"assignment": {"course":"C","section":"01","term":"t","name":"n",
            "org":"O","repo_prefix":"p-","total_points":100}}
    f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    yaml.safe_dump(data, f); f.close()
    m = load_manifest(Path(f.name))
    assert m.autograde is None
    assert m.docs == []

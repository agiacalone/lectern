# tests/test_recon_writeup_persist.py
import json
from pathlib import Path
from lectern.recon_docs import recon_doc
from lectern.recon_record import RepoRecord, record_to_dict
from lectern.recon_bundle import write_bundle

def test_recon_doc_captures_body(tmp_path):
    p = tmp_path / "WRITEUP.md"
    p.write_text("---\nhonor: X\n---\n# Grimoire\nWard I broke via ECB determinism.\n")
    d = recon_doc(p, label="grimoire")
    assert d.present and "ECB determinism" in d.body
    assert "honor: X" not in d.body  # frontmatter stripped

def test_bundle_persists_writeup_and_keeps_json_lean(tmp_path):
    p = tmp_path / "WRITEUP.md"
    p.write_text("---\nhonor: X\n---\n# Grimoire\nWard I notes.\n")
    rec = RepoRecord(github_id="harleyq", student="Harley Quinn", repo="r",
                     docs={"grimoire": recon_doc(p, label="grimoire")})
    write_bundle([rec], tmp_path / "out", lab_name="L", total_points=30)
    assert (tmp_path / "out" / "writeups" / "harleyq.md").read_text().strip() == "# Grimoire\nWard I notes."
    j = json.loads((tmp_path / "out" / "repos" / "harleyq.json").read_text())
    assert "body" not in j["docs"]["grimoire"]   # body not bloating the JSON

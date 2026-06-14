from pathlib import Path
from lectern.recon_docs import recon_doc, DocRecon

WRITEUP = """---
honor: SOLDIER-abc123
sources:
  - https://en.wikipedia.org/wiki/Padding_oracle_attack
---
# Grimoire
## Ward I
ECB leaks structure...
## Ward II
byte-at-a-time...
"""

def test_recon_doc_extracts_frontmatter_and_sections(tmp_path):
    p = tmp_path / "WRITEUP.md"; p.write_text(WRITEUP)
    d = recon_doc(p, label="grimoire")
    assert isinstance(d, DocRecon)
    assert d.present is True
    assert d.frontmatter.get("honor") == "SOLDIER-abc123"
    assert d.sources == 1
    assert "Ward I" in d.sections
    assert d.word_count > 5
    assert d.raw_path == str(p)

def test_recon_doc_missing(tmp_path):
    d = recon_doc(tmp_path / "nope.md", label="grimoire")
    assert d.present is False
    assert d.word_count == 0

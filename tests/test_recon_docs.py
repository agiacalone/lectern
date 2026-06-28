from pathlib import Path
from lectern.recon_docs import recon_doc, DocRecon, resolve_doc_path

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


# --- resolve_doc_path: tolerant deliverable lookup (case/path variants) ---
# Students name the writeup inconsistently; the strict repo/<file> check marked
# real submissions not-present (false doc-✗) and dropped them from the snapshot.

def test_resolve_exact_path_wins(tmp_path):
    (tmp_path / "writeup.md").write_text("x")
    assert resolve_doc_path(tmp_path, "writeup.md") == tmp_path / "writeup.md"

def test_resolve_case_variant_at_root(tmp_path):
    (tmp_path / "WRITEUP.md").write_text("x")
    assert resolve_doc_path(tmp_path, "writeup.md") == tmp_path / "WRITEUP.md"

def test_resolve_basename_in_subdir(tmp_path):
    (tmp_path / "submission").mkdir()
    (tmp_path / "submission" / "writeup.md").write_text("x")
    assert resolve_doc_path(tmp_path, "writeup.md") == tmp_path / "submission" / "writeup.md"

def test_resolve_fuzzy_md_containing_stem(tmp_path):
    f = tmp_path / "CECS 378 Lab Writeup.md"; f.write_text("x")
    assert resolve_doc_path(tmp_path, "writeup.md") == f

def test_resolve_prefers_root_over_subdir(tmp_path):
    (tmp_path / "WRITEUP.md").write_text("root")
    (tmp_path / "sub").mkdir(); (tmp_path / "sub" / "writeup.md").write_text("deep")
    assert resolve_doc_path(tmp_path, "writeup.md") == tmp_path / "WRITEUP.md"

def test_resolve_ignores_git_dir(tmp_path):
    g = tmp_path / ".git"; g.mkdir(); (g / "writeup.md").write_text("x")
    assert resolve_doc_path(tmp_path, "writeup.md") == tmp_path / "writeup.md"  # canonical (not found)

def test_resolve_ambiguous_fuzzy_returns_canonical(tmp_path):
    (tmp_path / "my writeup draft.md").write_text("a")
    (tmp_path / "final writeup notes.md").write_text("b")
    assert resolve_doc_path(tmp_path, "writeup.md") == tmp_path / "writeup.md"  # ambiguous -> canonical

def test_resolve_not_found_returns_canonical(tmp_path):
    (tmp_path / "README.md").write_text("x")
    assert resolve_doc_path(tmp_path, "writeup.md") == tmp_path / "writeup.md"

def test_resolve_then_recon_doc_reads_variant_body(tmp_path):
    # the integration the bug was about: a variant-named writeup is discovered
    # and its body is available to snapshot.
    (tmp_path / "WRITEUP.md").write_text("# Title\nreal content here\n")
    d = recon_doc(resolve_doc_path(tmp_path, "writeup.md"), label="writeup")
    assert d.present is True and "real content here" in d.body

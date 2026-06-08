"""Tests for pa/isa_publish.py — orchestrator for vault→Drive sync."""
import hashlib
from pathlib import Path
from unittest import mock

import pytest

from lectern import isa_publish
from lectern.isa_publish import (
    PublishConfig,
    PublishEntry,
    build_publish_manifest,
    check_publish,
    publish_to_drive,
)
from lectern.drive_auth import MCPBackend


# ---------------------------------------------------------------------------
# Fixture: a minimal bundle directory matching routing-table patterns.
# ---------------------------------------------------------------------------

@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    """Build a stub bundle under tmp_path with routing-matched files."""
    b = tmp_path / "bundle"
    (b / "exams").mkdir(parents=True)
    # exam keys + combined per-student packets
    (b / "exams" / "478-final-sp26-b_key.pdf").write_bytes(b"FAKE KEY PDF")
    (b / "exams" / "478-final-sp26-b_combined.pdf").write_bytes(b"FAKE COMBINED PDF")
    # something that should NOT match
    (b / "exams" / "scratch.txt").write_text("ignored")
    return b


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Build a stub vault root with an ISA delegation note."""
    v = tmp_path / "vault"
    (v / "notes").mkdir(parents=True)
    (v / "notes" / "isa-grading-delegation-spring-2026.md").write_text("# delegation")
    (v / "notes" / "isa-other-note.md").write_text("# not matching")
    return v


# ---------------------------------------------------------------------------
# build_publish_manifest
# ---------------------------------------------------------------------------

def test_build_publish_manifest_finds_exam_keys(bundle):
    cfg = PublishConfig(
        bundle_dir=bundle, course="CECS 478", term="sp26", section="04",
    )
    entries = build_publish_manifest(cfg)
    sources = [str(e.source) for e in entries]
    assert any("478-final-sp26-b_key.pdf" in s for s in sources)


def test_build_publish_manifest_routes_key_to_finals(bundle):
    cfg = PublishConfig(
        bundle_dir=bundle, course="CECS 478", term="sp26", section="04",
    )
    entries = build_publish_manifest(cfg)
    key_entry = next(
        e for e in entries if str(e.source).endswith("478-final-sp26-b_key.pdf")
    )
    assert key_entry.drive_path.startswith("ExampleDept-ISA/SP26/Finals/")


def test_build_publish_manifest_routes_combined_to_section(bundle):
    cfg = PublishConfig(
        bundle_dir=bundle, course="CECS 478", term="sp26", section="04",
    )
    entries = build_publish_manifest(cfg)
    combined_entry = next(
        e for e in entries if str(e.source).endswith("_combined.pdf")
    )
    assert "CECS 478 Section 04" in combined_entry.drive_path


def test_build_publish_manifest_computes_sha256(bundle):
    cfg = PublishConfig(
        bundle_dir=bundle, course="CECS 478", term="sp26", section="04",
    )
    entries = build_publish_manifest(cfg)
    key_entry = next(
        e for e in entries if str(e.source).endswith("478-final-sp26-b_key.pdf")
    )
    expected = "sha256:" + hashlib.sha256(b"FAKE KEY PDF").hexdigest()
    assert key_entry.source_hash == expected


def test_build_publish_manifest_includes_vault_wide_artifacts(bundle, vault):
    cfg = PublishConfig(
        bundle_dir=bundle, course="CECS 478", term="sp26", section="04",
        vault_root=vault,
    )
    entries = build_publish_manifest(cfg)
    sources = [str(e.source) for e in entries]
    assert any("isa-grading-delegation-spring-2026.md" in s for s in sources)


def test_build_publish_manifest_ignores_unmatched_files(bundle):
    cfg = PublishConfig(
        bundle_dir=bundle, course="CECS 478", term="sp26", section="04",
    )
    entries = build_publish_manifest(cfg)
    sources = [str(e.source) for e in entries]
    assert not any("scratch.txt" in s for s in sources)


# ---------------------------------------------------------------------------
# publish_to_drive — hash-skip + upload + update behavior
# ---------------------------------------------------------------------------

def test_publish_to_drive_uploads_when_no_prior_manifest(bundle, capsys):
    cfg = PublishConfig(
        bundle_dir=bundle, course="CECS 478", term="sp26", section="04",
    )
    entries = build_publish_manifest(cfg)
    backend = MCPBackend()
    updated = publish_to_drive(entries, backend, existing_manifest=None)
    for e in updated:
        assert e.drive_file_id  # got an ID assigned
    out = capsys.readouterr().out
    assert "MCP-PLANNED: upload" in out


def test_publish_to_drive_skips_unchanged_hash(bundle):
    cfg = PublishConfig(
        bundle_dir=bundle, course="CECS 478", term="sp26", section="04",
    )
    entries = build_publish_manifest(cfg)
    # Prior manifest matching exactly
    existing = {
        "publish": [
            {
                "source": str(e.source),
                "drive_path": e.drive_path,
                "source_hash": e.source_hash,
                "drive_file_id": f"PRIOR-{i}",
                "last_pushed": "2026-05-01T00:00:00-07:00",
            }
            for i, e in enumerate(entries)
        ]
    }
    backend = mock.MagicMock(spec=MCPBackend)
    backend.name = "mcp"
    publish_to_drive(entries, backend, existing_manifest=existing)
    backend.upload.assert_not_called()
    backend.update.assert_not_called()


def test_publish_to_drive_updates_when_hash_changes(bundle):
    cfg = PublishConfig(
        bundle_dir=bundle, course="CECS 478", term="sp26", section="04",
    )
    entries = build_publish_manifest(cfg)
    # Prior manifest with stale hash for one entry
    existing = {
        "publish": [
            {
                "source": str(entries[0].source),
                "drive_path": entries[0].drive_path,
                "source_hash": "sha256:stale-hash",
                "drive_file_id": "PRIOR-0",
                "last_pushed": "2026-05-01T00:00:00-07:00",
            }
        ]
    }
    backend = mock.MagicMock(spec=MCPBackend)
    backend.name = "mcp"
    publish_to_drive([entries[0]], backend, existing_manifest=existing)
    backend.update.assert_called_once()
    backend.upload.assert_not_called()


# ---------------------------------------------------------------------------
# check_publish — drift detection
# ---------------------------------------------------------------------------

def test_check_publish_clean_bundle_reports_ok(bundle, tmp_path):
    cfg = PublishConfig(
        bundle_dir=bundle, course="CECS 478", term="sp26", section="04",
    )
    entries = build_publish_manifest(cfg)
    import yaml
    publish_yaml = bundle / "isa-publish.yaml"
    publish_yaml.write_text(yaml.safe_dump({
        "publish": [
            {
                "source": str(e.source),
                "drive_path": e.drive_path,
                "source_hash": e.source_hash,
                "drive_file_id": f"PRIOR-{i}",
            }
            for i, e in enumerate(entries)
        ]
    }))
    # Backend reports matching md5 on Drive
    backend = mock.MagicMock(spec=MCPBackend)
    backend.name = "mcp"
    # md5 returns raw hex of the file (matches what check_publish recomputes)
    backend.file_md5.side_effect = lambda fid: hashlib.md5(
        next(e.source for e in entries if f"PRIOR-{entries.index(e)}" == fid).read_bytes()
    ).hexdigest()
    ok, fail, issues = check_publish(cfg, backend)
    assert fail == 0
    assert ok > 0


def test_check_publish_detects_edited_source(bundle, tmp_path):
    cfg = PublishConfig(
        bundle_dir=bundle, course="CECS 478", term="sp26", section="04",
    )
    entries = build_publish_manifest(cfg)
    import yaml
    publish_yaml = bundle / "isa-publish.yaml"
    publish_yaml.write_text(yaml.safe_dump({
        "publish": [
            {
                "source": str(entries[0].source),
                "drive_path": entries[0].drive_path,
                "source_hash": "sha256:stale-hash",
                "drive_file_id": "PRIOR-0",
            }
        ]
    }))
    backend = mock.MagicMock(spec=MCPBackend)
    backend.name = "mcp"
    backend.file_md5.return_value = "ignored"
    ok, fail, issues = check_publish(cfg, backend)
    assert fail >= 1
    assert any("edited" in i.lower() or "hash" in i.lower() for i in issues)

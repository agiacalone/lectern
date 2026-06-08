"""Tests for pa/drive_auth.py — 3-route Drive backend auto-detection."""
import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from lectern import drive_auth
from lectern.drive_auth import (
    MCPBackend,
    RcloneBackend,
    ServiceAccountBackend,
    detect_backend,
)


# ---------------------------------------------------------------------------
# MCPBackend — plans, doesn't execute
# ---------------------------------------------------------------------------

def test_mcp_backend_plans_upload(tmp_path, capsys):
    backend = MCPBackend()
    src = tmp_path / "key.pdf"
    src.write_text("fake pdf")
    file_id = backend.upload(src, "ExampleDept-ISA/SP26/Finals/key.pdf")
    out = capsys.readouterr().out
    assert file_id.startswith("MCP-PLANNED-")
    assert "MCP-PLANNED" in out
    assert "upload" in out
    assert "ExampleDept-ISA/SP26/Finals/key.pdf" in out


def test_mcp_backend_plans_update(tmp_path, capsys):
    backend = MCPBackend()
    src = tmp_path / "key.pdf"
    src.write_text("fake pdf v2")
    backend.update("1ABCxyz", src)
    out = capsys.readouterr().out
    assert "MCP-PLANNED" in out
    assert "update" in out
    assert "1ABCxyz" in out


def test_mcp_backend_file_md5_returns_none():
    backend = MCPBackend()
    # MCP backend can't verify md5 itself; returns None to force re-upload check
    # via this Claude session's MCP tools rather than the subagent's stub.
    assert backend.file_md5("1ABCxyz") is None


# ---------------------------------------------------------------------------
# ServiceAccountBackend — v1 stub
# ---------------------------------------------------------------------------

def test_service_account_backend_stub_raises(tmp_path):
    backend = ServiceAccountBackend()
    src = tmp_path / "x.pdf"
    src.write_text("x")
    with pytest.raises(NotImplementedError):
        backend.upload(src, "drive/path.pdf")


# ---------------------------------------------------------------------------
# RcloneBackend — subprocess construction
# ---------------------------------------------------------------------------

def test_rclone_backend_upload_constructs_command(tmp_path):
    backend = RcloneBackend()
    src = tmp_path / "key.pdf"
    src.write_text("pdf")
    drive_path = "ExampleDept-ISA/SP26/Finals/key.pdf"

    with mock.patch("subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        file_id = backend.upload(src, drive_path)
        run.assert_called_once()
        cmd = run.call_args[0][0]
        assert cmd[0] == "rclone"
        assert "copyto" in cmd
        assert str(src) in cmd
        assert f"gdrive:{drive_path}" in cmd
    # For rclone, drive_path serves as the implicit ID (no separate file_id).
    assert file_id == f"gdrive:{drive_path}"


def test_rclone_backend_file_md5_parses_hashsum(tmp_path):
    backend = RcloneBackend()
    with mock.patch("subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="deadbeef1234  ExampleDept-ISA/SP26/Finals/key.pdf\n",
            stderr="",
        )
        md5 = backend.file_md5("gdrive:ExampleDept-ISA/SP26/Finals/key.pdf")
        assert md5 == "deadbeef1234"


# ---------------------------------------------------------------------------
# detect_backend — routing
# ---------------------------------------------------------------------------

def test_detect_backend_prefers_mcp_env(monkeypatch):
    monkeypatch.setenv("MCP_DRIVE_AVAILABLE", "1")
    backend = detect_backend()
    assert backend.name == "mcp"


def test_detect_backend_falls_back_to_service_account(monkeypatch, tmp_path):
    monkeypatch.delenv("MCP_DRIVE_AVAILABLE", raising=False)
    sa_keyfile = tmp_path / "sa.json"
    sa_keyfile.write_text("{}")
    monkeypatch.setattr(drive_auth, "SA_KEYFILE", sa_keyfile)
    backend = detect_backend()
    assert backend.name == "service-account"


def test_detect_backend_falls_back_to_rclone(monkeypatch, tmp_path):
    monkeypatch.delenv("MCP_DRIVE_AVAILABLE", raising=False)
    monkeypatch.setattr(drive_auth, "SA_KEYFILE", tmp_path / "absent.json")

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["rclone", "listremotes"]:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="gdrive:\n", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    with mock.patch("subprocess.run", side_effect=fake_run):
        backend = detect_backend()
    assert backend.name == "rclone"


def test_detect_backend_errors_when_none_available(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("MCP_DRIVE_AVAILABLE", raising=False)
    monkeypatch.setattr(drive_auth, "SA_KEYFILE", tmp_path / "absent.json")

    def fake_run(cmd, *args, **kwargs):
        # Simulate rclone not installed
        raise FileNotFoundError("rclone not found")

    with mock.patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit):
            detect_backend()
    err = capsys.readouterr().err
    assert "rclone" in err or "service" in err or "MCP" in err

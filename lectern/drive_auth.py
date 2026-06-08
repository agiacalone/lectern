"""3-route Google Drive backend auto-detection for pa-isa-publish.

Three plausible paths to writing files to the ``ExampleDept-ISA/`` Drive
hierarchy. Each has different operational tradeoffs; ``pa-isa-publish`` picks
one at startup based on what's available.

  1. **MCPBackend** — when this Claude session has the Google Drive MCP
     connector mounted. The subagent that runs ``pa-isa-publish`` does **not**
     have MCP access, so this backend only PLANS uploads: it prints
     ``MCP-PLANNED: <action> <args>`` lines for the outer Claude session to
     parse and execute via its own MCP tools.

  2. **ServiceAccountBackend** — keyfile-driven google-api-python-client path.
     Needed when running unattended from cron (no human to OAuth). Stubbed in
     v1; activates when ``~/.config/google/sa-isa-publish.json`` exists.

  3. **RcloneBackend** — the user's existing ``gdrive:`` rclone remote. Already
     authenticated (the user runs ``rclone`` for other things). This is the
     pragmatic CLI path: ``rclone copyto`` for upload, ``rclone hashsum md5``
     for drift detection.

Detection order: env var → keyfile → rclone listremotes → exit with help.
"""
from __future__ import annotations

import itertools
import os
import subprocess
import sys
from pathlib import Path
from typing import Protocol, runtime_checkable


SA_KEYFILE = Path.home() / ".config" / "google" / "sa-isa-publish.json"


@runtime_checkable
class DriveBackend(Protocol):
    name: str

    def upload(self, src: Path, drive_path: str) -> str: ...
    def update(self, file_id: str, src: Path) -> None: ...
    def file_md5(self, file_id: str) -> str | None: ...


# ---------------------------------------------------------------------------
# MCP — planning only
# ---------------------------------------------------------------------------

class MCPBackend:
    """Plans MCP calls; doesn't execute them.

    The subagent has no MCP access. It prints ``MCP-PLANNED: <verb> <args>``
    lines that the outer Claude session parses and executes via its own MCP
    Drive tools.
    """

    name = "mcp"
    _counter = itertools.count(1)

    def upload(self, src: Path, drive_path: str) -> str:
        n = next(self._counter)
        print(f"MCP-PLANNED: upload {src} -> {drive_path}")
        return f"MCP-PLANNED-{n}"

    def update(self, file_id: str, src: Path) -> None:
        print(f"MCP-PLANNED: update {file_id} <- {src}")

    def file_md5(self, file_id: str) -> str | None:
        # Subagent can't query Drive metadata; outer session does the verify.
        return None


# ---------------------------------------------------------------------------
# Service account — v1 stub
# ---------------------------------------------------------------------------

class ServiceAccountBackend:
    """Service-account-keyed Drive client. Stubbed pending real keyfile setup."""

    name = "service-account"

    def upload(self, src: Path, drive_path: str) -> str:
        raise NotImplementedError(
            "ServiceAccountBackend.upload: v1 stub — drop a keyfile at "
            f"{SA_KEYFILE} and wire up google-api-python-client to activate."
        )

    def update(self, file_id: str, src: Path) -> None:
        raise NotImplementedError("ServiceAccountBackend.update: v1 stub")

    def file_md5(self, file_id: str) -> str | None:
        raise NotImplementedError("ServiceAccountBackend.file_md5: v1 stub")


# ---------------------------------------------------------------------------
# rclone — shell out to existing 'gdrive:' remote
# ---------------------------------------------------------------------------

class RcloneBackend:
    """Shells out to ``rclone`` against an existing ``gdrive:`` remote.

    rclone doesn't surface Drive's native file IDs through ``copyto``, so we
    use the full ``gdrive:<drive_path>`` URI as the implicit file identifier.
    Updates re-issue ``copyto`` (which overwrites by default).
    """

    name = "rclone"

    def upload(self, src: Path, drive_path: str) -> str:
        cmd = ["rclone", "copyto", str(src), f"gdrive:{drive_path}", "--metadata"]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return f"gdrive:{drive_path}"

    def update(self, file_id: str, src: Path) -> None:
        # file_id is the gdrive:<path> URI for this backend.
        target = file_id if file_id.startswith("gdrive:") else f"gdrive:{file_id}"
        cmd = ["rclone", "copyto", str(src), target, "--metadata"]
        subprocess.run(cmd, capture_output=True, text=True, check=True)

    def file_md5(self, file_id: str) -> str | None:
        target = file_id if file_id.startswith("gdrive:") else f"gdrive:{file_id}"
        try:
            result = subprocess.run(
                ["rclone", "hashsum", "md5", target],
                capture_output=True, text=True, check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        # rclone hashsum output: "<hash>  <path>\n"
        line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if not line:
            return None
        return line.split()[0]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _rclone_has_gdrive_remote() -> bool:
    try:
        result = subprocess.run(
            ["rclone", "listremotes"],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return False
    if result.returncode != 0:
        return False
    return any(line.strip() == "gdrive:" for line in result.stdout.splitlines())


def detect_backend() -> DriveBackend:
    """Auto-detect a usable Drive backend.

    Order:
      1. ``MCP_DRIVE_AVAILABLE`` env var → MCPBackend
      2. ``SA_KEYFILE`` exists → ServiceAccountBackend
      3. ``rclone listremotes`` shows ``gdrive:`` → RcloneBackend
      4. SystemExit with install/auth hints for all three.
    """
    if os.environ.get("MCP_DRIVE_AVAILABLE"):
        return MCPBackend()
    if SA_KEYFILE.exists():
        return ServiceAccountBackend()
    if _rclone_has_gdrive_remote():
        return RcloneBackend()

    msg = (
        "pa-isa-publish: no Google Drive backend available.\n"
        "  - MCP: set MCP_DRIVE_AVAILABLE=1 when running inside a Claude\n"
        "    session that has the Google Drive MCP connector.\n"
        f"  - Service account: drop a keyfile at {SA_KEYFILE} and grant it\n"
        "    write access to ExampleDept-ISA/.\n"
        "  - rclone: install rclone, run `rclone config` to add a 'gdrive:'\n"
        "    remote, then re-run pa-isa-publish.\n"
    )
    print(msg, file=sys.stderr)
    raise SystemExit(2)

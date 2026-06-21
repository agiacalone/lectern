# tests/integration/test_seam_readinglist.py
"""Seam A (live): Lectern -> Scriptorium reading-list CLI. Skip-gated."""
import os
import re
import shutil
import subprocess
from pathlib import Path
import pytest

pytestmark = pytest.mark.suite

SCRIP = Path(os.environ.get("LECTERN_SCRIPTORIUM_DIR", os.path.expanduser("~/git/scriptorium")))
CLI = SCRIP / "exam-reading-list-cli.js"
HAVE_NODE = shutil.which("node") is not None

requires_scriptorium = pytest.mark.skipif(
    not (HAVE_NODE and CLI.is_file()),
    reason="node + scriptorium exam-reading-list-cli.js not available",
)


def _normalize(md: str) -> str:
    # Drop volatile lines (timestamps, absolute paths) before comparison.
    out = []
    for line in md.splitlines():
        if re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", line):  # ISO timestamp
            continue
        line = line.replace(str(SCRIP), "<SCRIPTORIUM>")
        out.append(line.rstrip())
    return "\n".join(out).strip()


@requires_scriptorium
def test_readinglist_seam_runs_and_matches_golden(tmp_path, fixtures_dir):
    main = fixtures_dir / "readinglist/topic_demo/topic_demo_lecture_main.md"
    out = tmp_path / "products"; out.mkdir()
    subprocess.run(
        ["node", str(CLI), "--exam-name", "Demo Exam", "--slug", "demo_exam",
         "--course", "CECS 378", "--term", "su26", "--out", str(out),
         "--mains", str(main)],
        check=True, capture_output=True, text=True,
    )
    produced = (out / "demo_exam_reading_list.md")
    assert produced.is_file(), "CLI did not emit the reading list"
    golden = fixtures_dir / "readinglist/demo_exam_reading_list.golden.md"
    assert _normalize(produced.read_text()) == _normalize(golden.read_text())

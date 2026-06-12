import os
import subprocess
import pytest


@pytest.fixture
def mk_repo():
    """Factory: mk_repo(tmp_path, commits) -> repo path.
    commits: list of (iso_datetime, {filename: content})."""
    def _build(tmp_path, commits):
        repo = tmp_path / "r"; repo.mkdir()
        env = {**os.environ, "GIT_AUTHOR_NAME": "stu", "GIT_AUTHOR_EMAIL": "s@e.x",
               "GIT_COMMITTER_NAME": "stu", "GIT_COMMITTER_EMAIL": "s@e.x"}
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        for dt, files in commits:
            for fn, content in files.items():
                (repo / fn).write_text(content)
            env2 = {**env, "GIT_AUTHOR_DATE": dt, "GIT_COMMITTER_DATE": dt,
                    "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "commit.gpgsign",
                    "GIT_CONFIG_VALUE_0": "false"}
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", f"c {dt}"], cwd=repo, env=env2, check=True)
        return repo
    return _build

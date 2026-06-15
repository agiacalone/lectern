import os
import subprocess
import pytest


@pytest.fixture(autouse=True, scope="session")
def _disable_git_signing():
    """Make every git subprocess commit/tag without GPG signing.

    Tests build throwaway repos and commit into them; they must pass regardless
    of the developer's global git config. A contributor with
    ``commit.gpgsign=true`` (and no TTY available for the passphrase) would
    otherwise hit ``gpg: cannot open '/dev/tty'`` and fail ~a dozen tests.
    Exported via ``GIT_CONFIG_*`` so it reaches subprocesses that inherit env."""
    overrides = {
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false",
        "GIT_CONFIG_KEY_1": "tag.gpgsign", "GIT_CONFIG_VALUE_1": "false",
    }
    saved = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


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
            # signing is disabled session-wide by _disable_git_signing
            env2 = {**env, "GIT_AUTHOR_DATE": dt, "GIT_COMMITTER_DATE": dt}
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", f"c {dt}"], cwd=repo, env=env2, check=True)
        return repo
    return _build

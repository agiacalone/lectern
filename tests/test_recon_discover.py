from pathlib import Path
from lectern.recon_discover import discover_repos, RepoRef

FIX = Path(__file__).parent / "fixtures" / "recon" / "github.csv"

def test_discover_builds_repo_refs():
    refs = discover_repos(FIX, repo_prefix="cecs-378-su26-01-lab-01-symmetric-crypto-")
    assert all(isinstance(r, RepoRef) for r in refs)
    by_id = {r.github_id: r for r in refs}
    assert by_id["riddle-me-this"].repo == "cecs-378-su26-01-lab-01-symmetric-crypto-riddle-me-this"
    assert by_id["riddle-me-this"].student == "Edward Nashton"
    assert len(refs) == 2


def test_discover_uses_canonical_name(tmp_path):
    from lectern.recon_discover import discover_repos
    csv_path = tmp_path / "roster.csv"
    csv_path.write_text("student_id,canonical_name,github_username,source\n"
                        "040100203,Barbara Gordon,lucfox,classroom-lab01\n")
    refs = discover_repos(csv_path, repo_prefix="pre-")
    assert refs[0].student == "Barbara Gordon"
    assert refs[0].repo == "pre-lucfox"


# --- Classroom 50 roster shape -------------------------------------------
# A C50 roster.csv carries BOTH `username` (the login) and `github_id` (the
# immutable NUMERIC id), and splits the name across first_name/last_name.
# A legacy GitHub Classroom roster put the LOGIN in `github_id`, so the two
# formats collide on that column name and precedence is what separates them.

C50_HEADER = "username,first_name,last_name,email,section,github_id,role\n"


def test_discover_c50_roster_prefers_username_over_numeric_github_id(tmp_path):
    """Reading github_id first would name the repo `<prefix>-1548364`."""
    csv_path = tmp_path / "roster.csv"
    csv_path.write_text(C50_HEADER +
                        "agiacalone,Anthony,Giacalone,,section-1,1548364,student\n")
    refs = discover_repos(csv_path, repo_prefix="c50-tst0-lab-01-")
    assert len(refs) == 1
    assert refs[0].github_id == "agiacalone"
    assert refs[0].repo == "c50-tst0-lab-01-agiacalone"


def test_discover_c50_roster_composes_name_from_first_last(tmp_path):
    csv_path = tmp_path / "roster.csv"
    csv_path.write_text(C50_HEADER +
                        "bruce-wayne,Bruce,Wayne,,section-1,,student\n")
    refs = discover_repos(csv_path, repo_prefix="pre-")
    assert refs[0].student == "Bruce Wayne"


def test_discover_c50_roster_keeps_rows_with_unresolved_github_id(tmp_path):
    """A blank numeric github_id must not drop the student from the population."""
    csv_path = tmp_path / "roster.csv"
    csv_path.write_text(C50_HEADER +
                        "bruce-wayne,Bruce,Wayne,,section-1,,student\n"
                        "dick-grayson,Dick,Grayson,,section-1,,student\n")
    refs = discover_repos(csv_path, repo_prefix="pre-")
    assert [r.repo for r in refs] == ["pre-bruce-wayne", "pre-dick-grayson"]


def test_discover_legacy_github_id_login_still_wins_when_no_username(tmp_path):
    """Back-compat: legacy rosters store the LOGIN in github_id and have no
    `username` column, so behavior there must be unchanged."""
    csv_path = tmp_path / "roster.csv"
    csv_path.write_text("github_id,name\nbruce-wayne,Bruce Wayne\n")
    refs = discover_repos(csv_path, repo_prefix="cecs-378-su26-01-lab-03-")
    assert refs[0].github_id == "bruce-wayne"
    assert refs[0].repo == "cecs-378-su26-01-lab-03-bruce-wayne"
    assert refs[0].student == "Bruce Wayne"


def test_discover_explicit_github_username_outranks_c50_username(tmp_path):
    """`github_username` stays top of the chain as the explicit override."""
    csv_path = tmp_path / "roster.csv"
    csv_path.write_text("username,github_username,first_name,last_name\n"
                        "campus-sso-id,reallogin,Barbara,Gordon\n")
    refs = discover_repos(csv_path, repo_prefix="pre-")
    assert refs[0].repo == "pre-reallogin"

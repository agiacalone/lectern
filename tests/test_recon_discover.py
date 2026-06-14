from pathlib import Path
from lectern.recon_discover import discover_repos, RepoRef

FIX = Path(__file__).parent / "fixtures" / "recon" / "github.csv"

def test_discover_builds_repo_refs():
    refs = discover_repos(FIX, repo_prefix="cecs-378-su26-01-lab-01-symmetric-crypto-")
    assert all(isinstance(r, RepoRef) for r in refs)
    by_id = {r.github_id: r for r in refs}
    assert by_id["ChaoticNerd"].repo == "cecs-378-su26-01-lab-01-symmetric-crypto-ChaoticNerd"
    assert by_id["ChaoticNerd"].student == "C. Nerd"
    assert len(refs) == 2


def test_discover_uses_canonical_name(tmp_path):
    from lectern.recon_discover import discover_repos
    csv_path = tmp_path / "roster.csv"
    csv_path.write_text("student_id,canonical_name,github_username,source\n"
                        "418749197,Alfreda Pennyworth,gh-user-18,classroom-lab01\n")
    refs = discover_repos(csv_path, repo_prefix="pre-")
    assert refs[0].student == "Alfreda Pennyworth"
    assert refs[0].repo == "pre-gh-user-18"

from lectern.recon_links import repo_links

def test_repo_links_full():
    L = repo_links(org="Giacalone-CECS",
                   repo="cecs-378-su26-01-lab-01-symmetric-crypto-ChaoticNerd",
                   grading_commit="abc123", doc_path="student/WRITEUP.md")
    base = "https://github.com/Giacalone-CECS/cecs-378-su26-01-lab-01-symmetric-crypto-ChaoticNerd"
    assert L["repo"] == base
    assert L["docs"] == f"{base}/blob/abc123/student/WRITEUP.md"
    assert L["feedback_pr"] == f"{base}/pull/1"
    assert L["feedback_branch"] == f"{base}/tree/feedback"

def test_repo_links_no_commit_uses_default_branch():
    L = repo_links(org="O", repo="r", grading_commit=None, doc_path="student/WRITEUP.md")
    assert L["docs"] == "https://github.com/O/r/blob/main/student/WRITEUP.md"

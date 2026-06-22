from lectern.feedback_sanitize import lint_student_comment

NAMES = ["Basil Karlo", "Alfreda Pennyworth", "gh-user-06"]


def test_clean_passes():
    assert lint_student_comment(
        "Full clear across all wards; strong padding-oracle writeup.",
        cohort_names=NAMES) == []


def test_flags_internal_jargon():
    tags = lint_student_comment(
        "Triage REVIEW; honor-gate failed; digest abstained.", cohort_names=NAMES)
    assert "internal-jargon" in tags


def test_flags_cross_student_name():
    tags = lint_student_comment("Better than Basil Karlo's attempt.", cohort_names=NAMES)
    assert "cross-student" in tags


def test_jargon_is_word_boundary():
    # "flagging" must NOT trip the "flag" token
    assert lint_student_comment("Consider flagging weak ciphers.", cohort_names=NAMES) == []

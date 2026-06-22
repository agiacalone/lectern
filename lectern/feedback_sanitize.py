"""Deterministic lint guarding student-facing feedback text.

Run at digest-merge and again at deliver-time: a hit withholds the comment from
delivery. Internal grading notes must never reach students; cross-student
leakage is the worst failure mode.
"""
import re

# Internal tokens that must never reach students. Deliberately EXCLUDES words
# that collide with legitimate crypto vocabulary — "oracle" (padding oracle),
# "digest" (message digest), "review"/"flag" (ordinary verbs) — to avoid
# censoring real feedback. Cross-student leakage is handled separately by name.
JARGON = [
    "honor-gate", "honor gate", "triage", "advisory", "screening",
    "abstain", "needs-human-read", "partial-ward",
]


def lint_student_comment(text: str, *, cohort_names) -> list:
    """Return violation tags (empty == clean): 'internal-jargon', 'cross-student'."""
    tags = []
    low = text.lower()
    for tok in JARGON:
        if re.search(rf"(?<!\w){re.escape(tok)}(?!\w)", low):
            tags.append("internal-jargon")
            break
    for name in cohort_names:
        if name and name.lower() in low:
            tags.append("cross-student")
            break
    return tags

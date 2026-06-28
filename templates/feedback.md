<!--
Reference skeleton for the per-student FEEDBACK.md emitted by `reg-lab-report deliver`.
Digest path (--cohort): rendered by feedback_deliver.render_feedback_md (Wards/Grimoire).
Note path (--from-note): rendered by feedback_deliver.render_feedback_md_from_note —
the Component table loops over N components parsed from the grading-round note
(see lectern/feedback_note.py + docs/design/feedback-from-note.md).
-->
# {{lab}} — Feedback

**Total: {{total}} / {{grand}}**

| Component | Score |
| --- | --: |
| Wards (autograder) | {{points}} / {{auto_max}} |
| Grimoire (writeup) | {{writeup_score}} / {{writeup_max}} |

## Comments
{{student_comment}}

---
*{{course}} · {{term}} · §{{section}} — graded by Prof. Giacalone*

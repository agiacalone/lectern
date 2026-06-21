# LMS Suite — Release Compatibility Matrix

The coordinated release pins of **Lectern · Scriptorium · Oracle**. `reg-suite-check`
(→ `python -m lectern.suite_check`) verifies the installed component versions against
the ranges below; CI runs it via `tests/integration/test_seam_versions.py`.

```yaml
suite: "LMS Suite"
release: "v0.1.0-rc1"
components:
  lectern:     ">=0.1.0,<0.2"
  scriptorium: ">=0.1.0,<0.2"
  oracle:      ">=0.1.0,<0.2"
seam_contracts:
  reading_list: 1     # reg-exam-readinglist CLI arg contract
  autograde:    1     # result.json schema:1
  question_bank: 0    # KNOWN GAP — not a stable contract yet (see lms-suite-integration.md)
```

See [docs/design/lms-suite-integration.md](docs/design/lms-suite-integration.md) for the seam contracts.

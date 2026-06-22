# Integration fixtures — provenance

Golden inputs for the LMS-suite seam tests. **Do not hand-edit; regenerate.**

| Fixture | Producing tool | Contract | Regen |
|---|---|---|---|
| `autograde/result_*.json` | Oracle gradebox `result.json` (schema:1) | autograde v1 | authored by hand from Oracle's documented schema; mirror of `oracle/examples/sample-outputs/result.json` |
| `qbank/scriptorium_bank.md` | Scriptorium `question-bank.js` | question_bank (gap) | `node <scriptorium>/generate.js ... --artifact question-bank` |
| `qbank/lectern_bank.md` | Lectern `reg-qbank` YAML-fenced format | qbank-lectern | hand-authored to lectern/qbank.py schema |
| `readinglist/` | Scriptorium `exam-reading-list-cli.js` | reading_list v1 | `tests/integration/regen.sh` |

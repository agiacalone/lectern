# Contributing to lectern

lectern is an MIT-licensed open-source project. Contributions are welcome.

## Development setup

```bash
git clone https://github.com/agiacalone/lectern
cd lectern
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the tests

```bash
pytest
```

The test suite requires no external services. Exam-build tests require a
`pdflatex` installation (TeX Live or MiKTeX); they are automatically skipped
if `pdflatex` is not found.

## Code style

- Python 3.11+ type annotations on all public functions
- `from __future__ import annotations` in every module
- `dataclass` for configuration and result types
- Docstrings on every public function and module
- No external runtime dependencies beyond `pyyaml`, `jsonschema`, and `vaultkit`

## Submitting changes

1. Fork the repo and create a feature branch.
2. Write or update tests to cover your changes.
3. Run `pytest` — all tests must pass.
4. Open a pull request with a clear description of what changed and why.

## Reporting issues

Open a GitHub issue. Include the command you ran, the error output, and the
Python version and OS. For exam-build issues, include the relevant lines of
your `.tex` or `exam.build.yaml` (redact any real student names or IDs).

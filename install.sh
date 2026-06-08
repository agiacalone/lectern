#!/usr/bin/env bash
# Install lectern: create a local venv, install editable, and create reg-* wrappers.
set -euo pipefail

LECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$LECT_DIR/.venv"
BIN="$HOME/bin"
mkdir -p "$BIN"

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

"$VENV_PIP" install -e "$LECT_DIR"

make_wrapper() {  # $1=wrapper-name  $2=module
  local path="$BIN/$1"
  printf '#!/usr/bin/env bash\nexec "%s" -m %s "$@"\n' "$VENV_PY" "$2" > "$path"
  chmod +x "$path"
  echo "wrote $path"
}

make_wrapper reg-term-create           lectern.term_create
make_wrapper reg-term-finalize         lectern.term_finalize
make_wrapper reg-term-archive          lectern.term_archive
make_wrapper reg-gradebook             lectern.gradebook
make_wrapper reg-exam-build            lectern.exam_build
make_wrapper reg-exam-verify           lectern.exam_verify
make_wrapper reg-lms-grades-import     lectern.lms_grades
make_wrapper reg-lms-roster-import     lectern.lms_roster
make_wrapper reg-classroom-roster-seed lectern.classroom_seed
make_wrapper reg-github-bind           lectern.github_bind
make_wrapper reg-isa-publish           lectern.isa_publish

echo "lectern installed. reg-* wrappers in $BIN."

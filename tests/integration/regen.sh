#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIP="${LECTERN_SCRIPTORIUM_DIR:-$HOME/git/scriptorium}"
OUT="$HERE/fixtures/readinglist/topic_demo/products"
mkdir -p "$OUT"
node "$SCRIP/exam-reading-list-cli.js" --exam-name "Demo Exam" --slug demo_exam \
  --course "CECS 378" --term su26 --out "$OUT" \
  --mains "$HERE/fixtures/readinglist/topic_demo/topic_demo_lecture_main.md"
cp "$OUT/demo_exam_reading_list.md" "$HERE/fixtures/readinglist/demo_exam_reading_list.golden.md"
echo "regenerated golden"

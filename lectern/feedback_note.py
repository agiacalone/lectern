"""Parse a grading-round report note's per-student feedback blocks into rows.

The vault note (`recon-<lab>/REPORT.md`) is the **authoritative** source of graded
feedback: one block per student under the per-student-feedback section, keyed by a
backtick-quoted github id. `reg-lab-report deliver --from-note` reads these rows
and renders each repo's `FEEDBACK.md` from them, so hand-authored feedback is never
re-derived from a digest cohort and clobbered.

Block grammar (the contract — see docs/design/feedback-from-note.md):

    ### <Display Name> — **<total> / <grand>**
    `<github_id>` · [repo](<url>)
    <Comp1> <n>/<max> · <Comp2> <n>/<max> · … · <CompK> +<n>/<max>
    _Comments:_ <student-facing prose, until the next ### / ## / EOF>

`__` (or `—`) anywhere a number is expected means "not graded yet": the row is
returned with ``graded=False`` so callers can skip it (delivery only ships graded
rows). A leading ``+`` on a component marks extra credit.
"""
import re

# Trailing `(?:\s.*)?$` tolerates an at-a-glance suffix after the closing `**`
# (e.g. `· ACE +14/15`). Anchoring strictly on `**$` silently skipped such heads,
# dropping the student from delivery with no error.
_HEAD = re.compile(r"^###\s+(.+?)\s+—\s+\*\*\s*(.+?)\s*/\s*(\d+)\s*\*\*(?:\s.*)?$")
_GID = re.compile(r"`([^`]+)`")
_COMPTOK = re.compile(r"^\s*(.+?)\s+(\+?)(\d+|__|—)\s*/\s*(\d+)\s*$")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def _num(s):
    return None if s in ("__", "—") else int(s)


def _parse_scoreline(line):
    """A '·'-delimited line of `Label n/max` tokens → component dicts, or None."""
    comps = []
    for tok in line.split("·"):
        m = _COMPTOK.match(tok)
        if not m:
            return None
        label, ec, score, mx = m.groups()
        comps.append({"label": label.strip(), "score": _num(score),
                      "max": int(mx), "ec": ec == "+"})
    return comps or None


def parse_feedback_note(path):
    """Return one row dict per `###` student block found in the note.

    row = {github_id, student, total (int|None), grand (int),
           components: [{label, score (int|None), max, ec}], comment (str),
           graded (bool)}
    Blocks without a backtick-quoted github id are skipped (not a student block).
    """
    lines = open(path).read().splitlines()
    rows, i, n = [], 0, len(lines)
    while i < n:
        m = _HEAD.match(lines[i])
        if not m:
            i += 1
            continue
        name, total_s, grand = m.group(1).strip(), m.group(2).strip(), int(m.group(3))
        j = i + 1
        body = []
        while j < n and not lines[j].startswith("### ") and not lines[j].startswith("## "):
            body.append(lines[j])
            j += 1
        block = "\n".join(body)
        gidm = _GID.search(block)            # first backtick token = the gid line
        gid = gidm.group(1).strip() if gidm else None
        components = next((c for c in (_parse_scoreline(ln) for ln in body) if c), None)
        comment = ""
        cm = re.search(r"_Comments:_\s*(.*)", block, re.S)
        if cm:
            comment = _HTML_COMMENT.sub("", cm.group(1)).strip()
        graded = "_" not in total_s and "—" not in total_s
        if gid:
            rows.append({"github_id": gid, "student": name,
                         "total": int(total_s) if graded else None, "grand": grand,
                         "components": components or [], "comment": comment,
                         "graded": graded})
        i = j
    return rows

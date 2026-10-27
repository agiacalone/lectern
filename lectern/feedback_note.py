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

The block `reg-lab-report render` writes is also accepted, so a rendered
`REPORT.md` can be delivered without hand conversion:

    ### <github_id> — **<total> / <grand>**
    *github: [`<github_id>`](<url>) · Auto <n>/<max> · Writeup <n>/<max> · [Feedback PR](<url>)*

    > <student-facing prose, every line quoted>

    <!-- internal: … -->

The `github:` and link tokens on the score line are decoration, and the comment
is the block quote when there is no `_Comments:_` marker. The rendered
non-submission quote `_no submission_` is not a comment.
"""
import re

# Trailing `(?:\s.*)?$` tolerates an at-a-glance suffix after the closing `**`
# (e.g. `· ACE +14/15`). Anchoring strictly on `**$` silently skipped such heads,
# dropping the student from delivery with no error.
_HEAD = re.compile(r"^###\s+(.+?)\s+—\s+\*\*\s*(.+?)\s*/\s*(\d+)\s*\*\*(?:\s.*)?$")
_GID = re.compile(r"`([^`]+)`")
_COMPTOK = re.compile(r"^\s*(.+?)\s+(\+?)(\d+|__|—)\s*/\s*(\d+)\s*$")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
# Rendered score-line decoration: the `github: [`id`](url)` lead and bare
# markdown links such as `[Feedback PR](url)`. Skipped, not parsed as components.
_DECOR = re.compile(r"^\s*(?:github:\s*\S.*|\[[^\]]*\]\([^)]*\))\s*$")
_NO_SUBMISSION = "_no submission_"


def _num(s):
    return None if s in ("__", "—") else int(s)


def _parse_scoreline(line):
    """A '·'-delimited line of `Label n/max` tokens → component dicts, or None.

    A rendered line wrapped in `*…*` with decoration tokens is accepted; any
    other token that is not a component rejects the whole line, so prose with a
    `·` in it is never mistaken for scores.
    """
    s = line.strip()
    if len(s) > 1 and s.startswith("*") and s.endswith("*") and not s.startswith("**"):
        s = s[1:-1]
    comps = []
    for tok in s.split("·"):
        if _DECOR.match(tok):
            continue
        m = _COMPTOK.match(tok)
        if not m:
            return None
        label, ec, score, mx = m.groups()
        comps.append({"label": label.strip(), "score": _num(score),
                      "max": int(mx), "ec": ec == "+"})
    return comps or None


def _unquote(text):
    """Drop a block-quote prefix from every line (`> x` → `x`, `>` → blank)."""
    return "\n".join(re.sub(r"^\s*>\s?", "", ln) for ln in text.splitlines())


def _comment(block):
    """The student-facing comment: after `_Comments:_`, else the block quote."""
    text = _HTML_COMMENT.sub("", block)
    cm = re.search(r"^([ \t]*>?)[ \t]*_Comments:_[ \t]*(.*)", text, re.S | re.M)
    if cm:   # a quoted marker (the rendered placeholder) quotes its prose too
        return (_unquote(cm.group(2)) if ">" in cm.group(1) else cm.group(2)).strip()
    quoted = [ln for ln in text.splitlines() if ln.lstrip().startswith(">")]
    comment = _unquote("\n".join(quoted)).strip()
    return "" if comment == _NO_SUBMISSION else comment


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
        comment = _comment(block)
        graded = "_" not in total_s and "—" not in total_s
        if gid:
            rows.append({"github_id": gid, "student": name,
                         "total": int(total_s) if graded else None, "grand": grand,
                         "components": components or [], "comment": comment,
                         "graded": graded})
        i = j
    return rows

"""reg-admin-form — fill a CSULB administrative form from the vault's own records.

The forms are the problem this solves. A Notice of Absence is a DocuSign packet
with no dropdowns that nonetheless wants exact course numbers, class numbers,
rooms, meeting times, and a coverage plan — facts the vault already holds in the
term-spec and the class-notes, and that are tedious and error-prone to retype
from memory at 7am on a sick day.

A *form profile* (YAML) declares the fields one form asks for and where each
value comes from. The engine resolves those sources, then emits three products:

- ``FORM.md``   — a labeled copy/paste block, one field per section, in the
                  form's own order, so filling DocuSign is a paste-per-box job
- ``EMAIL.md``  — the routing email, addressed per the profile
- ``record.yaml`` — the machine record, so leave taken this year is countable

Adding a form means writing a profile, not writing code.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import yaml

from lectern.class_calendar import (
    AffectedDay,
    all_meetings,
    contact_hours,
    meetings_in_range,
)
from lectern.term_spec import load_term_spec

BUILTIN_FORMS = Path(__file__).parent / "references" / "forms"
FORMS_DIRNAME = "admin-forms"
NEEDS_INPUT = "«NEEDS INPUT»"


class AdminFormError(Exception):
    """Raised for a bad profile, an unknown form, or an unresolvable field."""


# ─────────────────────────────── loading ────────────────────────────────────

def forms_dir(vault_root: Path) -> Path:
    """Where a vault keeps its form profiles, identity, and absence records."""
    return Path(vault_root) / "classes" / FORMS_DIRNAME


def find_profile(name: str, vault_root: Path | None) -> Path:
    """Resolve a form name to a profile path — vault copy wins over built-in.

    A path that exists is taken as-is, so a one-off profile can live anywhere.
    """
    direct = Path(name)
    if direct.suffix in (".yaml", ".yml") and direct.exists():
        return direct
    stem = direct.stem if direct.suffix else name
    candidates = []
    if vault_root:
        candidates.append(forms_dir(vault_root) / f"{stem}.form.yaml")
    candidates.append(BUILTIN_FORMS / f"{stem}.form.yaml")
    for path in candidates:
        if path.exists():
            return path
    known = ", ".join(sorted(p.stem.replace(".form", "")
                             for p in BUILTIN_FORMS.glob("*.form.yaml")))
    raise AdminFormError(f"no form profile named {name!r}. Built-in: {known}")


def load_profile(path: Path) -> dict:
    """Load and sanity-check a form profile."""
    profile = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    for key in ("form", "title", "fields"):
        if key not in profile:
            raise AdminFormError(f"{path}: profile is missing required key {key!r}")
    if not isinstance(profile["fields"], list) or not profile["fields"]:
        raise AdminFormError(f"{path}: 'fields' must be a non-empty list")
    for i, fld in enumerate(profile["fields"]):
        if "label" not in fld:
            raise AdminFormError(f"{path}: field #{i + 1} has no 'label'")
        fld.setdefault("key", _slug_key(fld["label"]))
    return profile


def load_identity(vault_root: Path | None) -> dict:
    """Load the instructor identity block, or an empty dict when absent."""
    if not vault_root:
        return {}
    path = forms_dir(vault_root) / "identity.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _slug_key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(label).lower()).strip("-")


# ─────────────────────────────── dates ──────────────────────────────────────

def parse_dates(text: str) -> list[date]:
    """Parse ``--dates``: a day, a ``A..B`` span, or a comma-separated mix."""
    days: list[date] = []
    for chunk in str(text).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ".." in chunk:
            lo, hi = (c.strip() for c in chunk.split("..", 1))
            start, end = date.fromisoformat(lo), date.fromisoformat(hi)
            if end < start:
                raise AdminFormError(f"date range ends before it starts: {chunk}")
            cur = start
            while cur <= end:
                days.append(cur)
                cur = cur.fromordinal(cur.toordinal() + 1)
        else:
            days.append(date.fromisoformat(chunk))
    if not days:
        raise AdminFormError("no dates given")
    return sorted(set(days))


def humanize_date(day: date) -> str:
    """``"Thursday, September 10, 2026"`` — how a form wants a date spelled."""
    return f"{day.strftime('%A')}, {day.strftime('%B')} {day.day}, {day.year}"


def humanize_span(days: list[date]) -> str:
    """One date, or ``"A through B"``, or a comma list when non-contiguous."""
    if len(days) == 1:
        return humanize_date(days[0])
    contiguous = all(
        (days[i + 1].toordinal() - days[i].toordinal()) == 1
        for i in range(len(days) - 1)
    )
    if contiguous:
        return f"{humanize_date(days[0])} through {humanize_date(days[-1])}"
    return "; ".join(humanize_date(d) for d in days)


# ─────────────────────────── syllabus topics ────────────────────────────────

_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}
_WEEK_ROW = re.compile(r"^\|\s*\*{0,2}([A-Z][a-z]{2})\s+(\d{1,2})\*{0,2}\s*\|(.+?)\|?\s*$")


def _syllabus_path(vault_root: Path, term: str, course: str, section: str) -> Path | None:
    """Find the syllabus note for one section, by its filename convention."""
    d = Path(vault_root) / "classes" / "syllabi" / term
    if not d.is_dir():
        return None
    num = str(course).split()[-1]
    pattern = f"cecs-{num}-{str(section).zfill(2)}-{term}-*"
    matches = sorted(d.glob(pattern + ".md"))
    return matches[0] if matches else None


def syllabus_topics(path: Path, year: int) -> dict[date, str]:
    """Parse a syllabus 'Week of | Subject' table into ``{monday: subject}``."""
    topics: dict[date, str] = {}
    in_table = False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if re.match(r"^\|\s*Week of\s*\|", line, re.I):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                if topics:
                    break
                in_table = False
                continue
            if re.match(r"^\|[\s|:-]+$", line):
                continue
            m = _WEEK_ROW.match(line.rstrip())
            if not m:
                continue
            mon, day, subject = m.group(1), int(m.group(2)), m.group(3)
            if mon not in _MONTHS:
                continue
            try:
                week_of = date(year, _MONTHS[mon], day)
            except ValueError:
                continue
            topics[week_of] = _clean_topic(subject)
    return topics


def _clean_topic(text: str) -> str:
    """Strip the table cell down to a phrase a form reader can parse."""
    text = re.sub(r"\[\[([^\]|]+\|)?([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"[*_`🅰🅱🅲⚠🚨]", "", text)
    return re.sub(r"\s+", " ", text).strip(" |·—-").strip()


def attach_topics(days: list[AffectedDay], vault_root: Path | None,
                  term: str, year: int) -> list[AffectedDay]:
    """Fill each meeting's ``topic`` from its section's syllabus schedule."""
    if not vault_root:
        return days
    cache: dict[tuple[str, str], dict[date, str]] = {}
    out: list[AffectedDay] = []
    for entry in days:
        meetings = []
        for meeting in entry.meetings:
            key = (meeting.course, meeting.section)
            if key not in cache:
                path = _syllabus_path(vault_root, term, *key)
                cache[key] = syllabus_topics(path, year) if path else {}
            monday = meeting.date.fromordinal(
                meeting.date.toordinal() - meeting.date.weekday())
            topic = cache[key].get(monday)
            meetings.append(
                meeting if topic is None
                else type(meeting)(**{**meeting.__dict__, "topic": topic})
            )
        entry.meetings = meetings
        out.append(entry)
    return out


# ─────────────────────────── the resolved context ───────────────────────────

@dataclass
class Context:
    """Everything a profile's ``source:`` expressions can read."""

    profile: dict
    identity: dict
    spec: dict
    days: list[AffectedDay]
    absence_dates: list[date]
    leave_type: dict
    overrides: dict
    hours: float | None
    today: date

    # ── derived views ──
    @property
    def meetings(self):
        return all_meetings(self.days)

    @property
    def affected_sections(self) -> list[str]:
        seen: list[str] = []
        for m in self.meetings:
            if m.label not in seen:
                seen.append(m.label)
        return seen

    def classes_table(self) -> str:
        """The affected-meetings table — the part these forms actually want."""
        if not self.meetings:
            return "No scheduled class meetings fall on the requested date(s)."
        rows = ["| Date | Course | Class # | Time | Room | Topic scheduled |",
                "| --- | --- | --- | --- | --- | --- |"]
        for m in self.meetings:
            rows.append(
                f"| {m.date.isoformat()} ({m.date.strftime('%a')}) | {m.label} "
                f"| {m.class_number or '—'} | {m.pattern.time_range or '—'} "
                f"| {m.room or '—'} | {m.topic or '—'} |"
            )
        return "\n".join(rows)

    def classes_lines(self) -> str:
        """The same facts as plain lines, for a form box that eats Markdown."""
        if not self.meetings:
            return "None — no scheduled class meetings on the requested date(s)."
        out = []
        for m in self.meetings:
            bits = [f"{m.date.strftime('%a %m/%d')}", m.label,
                    f"class #{m.class_number}" if m.class_number else "",
                    m.pattern.time_range, m.room or ""]
            line = " · ".join(b for b in bits if b)
            if m.topic:
                line += f" — {m.topic}"
            out.append(line)
        return "\n".join(out)

    def skipped_days(self) -> str:
        """Days in the span that cost no class, and why — reviewers ask."""
        notes = [f"{d.weekday_abbr} {d.date.isoformat()}: {d.note}"
                 for d in self.days if not d.meetings]
        return "\n".join(notes)


# ─────────────────────────── source resolution ──────────────────────────────

def resolve(source, ctx: Context):
    """Resolve one field's ``source:`` into a string.

    Sources are dotted names into the context. ``literal:<text>`` is a fixed
    value; ``prompt`` means the value has to come from ``--set``.
    """
    if source is None:
        return NEEDS_INPUT
    text = str(source)
    if text.startswith("literal:"):
        return text[len("literal:"):].strip()
    if text == "prompt":
        return NEEDS_INPUT

    head, _, tail = text.partition(".")
    if head == "instructor":
        return _stringify(ctx.identity.get(tail))
    if head == "leave":
        return _stringify(ctx.leave_type.get(tail))
    if head == "term":
        return _stringify(ctx.spec.get(tail))
    if head == "today":
        return humanize_date(ctx.today) if tail == "long" else ctx.today.isoformat()
    if head == "absence":
        return _absence(tail, ctx)
    if head == "classes":
        return _classes(tail, ctx)
    raise AdminFormError(f"unknown source {source!r}")


def _absence(key: str, ctx: Context) -> str:
    days = ctx.absence_dates
    if key in ("dates", "span"):
        return humanize_span(days)
    if key == "dates-iso":
        return ", ".join(d.isoformat() for d in days)
    if key == "first":
        return days[0].isoformat()
    if key == "last":
        return days[-1].isoformat()
    if key == "first-long":
        return humanize_date(days[0])
    if key == "last-long":
        return humanize_date(days[-1])
    if key == "day-count":
        return str(len(days))
    if key == "hours":
        return "" if ctx.hours is None else _trim(ctx.hours)
    if key == "contact-hours":
        hours = contact_hours(ctx.days)
        return "" if hours is None else _trim(hours)
    raise AdminFormError(f"unknown source 'absence.{key}'")


def _classes(key: str, ctx: Context) -> str:
    if key == "table":
        return ctx.classes_table()
    if key in ("lines", "list"):
        return ctx.classes_lines()
    if key == "sections":
        return ", ".join(ctx.affected_sections) or "none"
    if key == "count":
        return str(len(ctx.meetings))
    if key == "section-count":
        return str(len(ctx.affected_sections))
    if key == "skipped":
        return ctx.skipped_days()
    raise AdminFormError(f"unknown source 'classes.{key}'")


def _trim(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _stringify(value) -> str:
    if value is None:
        return NEEDS_INPUT
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


def resolve_fields(ctx: Context) -> list[dict]:
    """Resolve every field in the profile, honouring the leave type and --set.

    Precedence is ``--set`` > leave-type default > the field's own ``source``.
    A leave type may also ``omit`` fields outright: a contractual personal
    holiday is not owed a justification, and a form that prints an empty
    "Reason" box invites volunteering one.
    """
    omit = set(ctx.leave_type.get("omit") or [])
    defaults = ctx.leave_type.get("defaults") or {}
    resolved = []
    for fld in ctx.profile["fields"]:
        key = fld["key"]
        if key in omit and key not in ctx.overrides:
            continue
        if key in ctx.overrides:
            value = ctx.overrides[key]
        elif key in defaults:
            value = defaults[key]
        else:
            value = resolve(fld.get("source"), ctx)
        resolved.append({
            "key": key,
            "label": fld["label"],
            "value": value,
            "hint": fld.get("hint"),
            "block": bool(fld.get("block")) or "\n" in str(value),
            "needs_input": str(value).strip() in ("", NEEDS_INPUT),
        })
    return resolved


# ─────────────────────────────── rendering ──────────────────────────────────

def render_form(ctx: Context, fields: list[dict]) -> str:
    """The copy/paste block — one labeled section per form field, in order."""
    p = ctx.profile
    out = [f"# {p['title']} — copy/paste block", ""]
    meta = [f"**Prepared** {humanize_date(ctx.today)}"]
    if p.get("authority"):
        meta.append(f"**Where** {p['authority']}")
    if p.get("submit-via"):
        meta.append(f"**Submit via** {p['submit-via']}")
    out += ["  \n".join(meta), ""]

    if ctx.leave_type.get("guidance"):
        out += ["> [!note] " + ctx.leave_type.get("label", "This leave type"),
                "> " + ctx.leave_type["guidance"].strip().replace("\n", "\n> "), ""]

    pending = [f for f in fields if f["needs_input"]]
    if pending:
        out += ["> [!warning] Fill these before submitting",
                "> " + ", ".join(f["label"] for f in pending), ""]

    if p.get("routing"):
        out += ["## Routing emails", "",
                "| Role | Email |", "| --- | --- |"]
        for r in p["routing"]:
            out.append(f"| {r.get('role', '')} | `{r.get('email', '')}` |")
        out.append("")

    out += ["## Fields", ""]
    for f in fields:
        out.append(f"### {f['label']}")
        if f["hint"]:
            out.append(f"*{f['hint']}*")
        out.append("")
        value = f["value"] if str(f["value"]).strip() else NEEDS_INPUT
        if f["block"]:
            out += [str(value), ""]
        else:
            out += ["```", str(value), "```", ""]

    if ctx.days:
        out += ["## Supporting detail — affected class meetings", "",
                ctx.classes_table(), ""]
        skipped = ctx.skipped_days()
        if skipped:
            out += ["Days in the span with no meeting:", "",
                    *[f"- {line}" for line in skipped.splitlines()], ""]
    return "\n".join(out).rstrip() + "\n"


def render_email(ctx: Context, fields: list[dict]) -> str:
    """The routing email, with the affected-class facts already in the body."""
    p = ctx.profile
    email = p.get("email") or {}
    values = {f["key"]: f["value"] for f in fields}
    # DocuSign signer routing and "who do I email" are different questions:
    # the form routes to the chair for signature, the heads-up goes to the
    # timekeeper who asked for it. A profile may state the email addressing
    # explicitly; otherwise fall back to the signer routing.
    if email.get("to") or email.get("cc"):
        to = _aslist(email.get("to"))
        cc = _aslist(email.get("cc"))
    else:
        to = [r["email"] for r in p.get("routing", []) if r.get("to")]
        cc = [r["email"] for r in p.get("routing", []) if not r.get("to")]
    subject = _expand(email.get("subject", p["title"]), values, ctx)
    body = _expand(email.get("body", ""), values, ctx)
    out = [f"# {p['title']} — email", "",
           f"**To:** {', '.join(to) or '—'}  ",
           f"**Cc:** {', '.join(cc) or '—'}  ",
           f"**Subject:** {subject}", "", "---", "", body.rstrip(), ""]
    return "\n".join(out)


def _aslist(value) -> list[str]:
    """Accept a profile's ``to:``/``cc:`` as a string or a list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [str(v) for v in value]


_TOKEN = re.compile(r"\{\{\s*([a-zA-Z0-9_.:-]+)\s*\}\}")


def _expand(template: str, values: dict, ctx: Context) -> str:
    """Expand ``{{field-key}}`` and ``{{source.expr}}`` inside profile text."""
    def sub(m):
        token = m.group(1)
        if token in values:
            return str(values[token])
        try:
            return str(resolve(token, ctx))
        except AdminFormError:
            return m.group(0)
    return _TOKEN.sub(sub, str(template))


def render_record(ctx: Context, fields: list[dict]) -> str:
    """The machine record — so 'have I used my personal day?' is answerable."""
    record = {
        "form": ctx.profile["form"],
        "title": ctx.profile["title"],
        "leave-type": ctx.leave_type.get("label", ctx.overrides.get("leave-type")),
        "dates": [d.isoformat() for d in ctx.absence_dates],
        "day-count": len(ctx.absence_dates),
        "hours": ctx.hours,
        "term": ctx.spec.get("term"),
        "prepared": ctx.today.isoformat(),
        "submitted": None,
        "affected-meetings": [
            {"date": m.date.isoformat(), "course": m.course, "section": m.section,
             "class-number": m.class_number, "room": m.room,
             "time": m.pattern.time_range, "topic": m.topic}
            for m in ctx.meetings
        ],
        "fields": {f["key"]: f["value"] for f in fields},
    }
    return yaml.dump(record, sort_keys=False, allow_unicode=True, width=100)


# ──────────────────────────────── driver ────────────────────────────────────

def build_context(args) -> Context:
    """Assemble the resolution context from CLI arguments + the vault."""
    vault_root = Path(args.vault_root) if args.vault_root else None
    profile = load_profile(find_profile(args.form, vault_root))
    identity = load_identity(vault_root)

    spec_path = Path(args.spec) if args.spec else None
    if spec_path is None and vault_root and args.term:
        for cand in (vault_root / "classes" / "semesters" / f"{args.term}.spec.yaml",
                     vault_root / "classes" / f"{args.term}.spec.yaml"):
            if cand.exists():
                spec_path = cand
                break
    if spec_path is None:
        raise AdminFormError(
            "no term-spec found — pass --spec, or --term with --vault-root")
    spec = load_term_spec(spec_path)

    dates = parse_dates(args.dates)
    days = meetings_in_range(spec, dates[0], dates[-1])
    days = [d for d in days if d.date in set(dates)]
    year = dates[0].year
    days = attach_topics(days, vault_root, spec.get("term", args.term or ""), year)

    types = profile.get("leave-types") or {}
    leave_type: dict = {}
    if args.type:
        if types and args.type not in types:
            raise AdminFormError(
                f"unknown leave type {args.type!r}. Profile offers: "
                + ", ".join(sorted(types)))
        leave_type = dict(types.get(args.type) or {})
        leave_type.setdefault("key", args.type)
        leave_type.setdefault("label", args.type.replace("-", " ").title())

    hours = args.hours
    if hours is None:
        per_day = profile.get("hours-per-day", 8)
        hours = float(per_day) * len(dates) if per_day else None

    overrides = {}
    for item in args.set or []:
        if "=" not in item:
            raise AdminFormError(f"--set expects key=value, got {item!r}")
        k, v = item.split("=", 1)
        overrides[k.strip()] = v
    if args.type:
        overrides.setdefault("leave-type", leave_type.get("label"))

    today = (date.fromisoformat(args.today) if args.today
             else datetime.now().date())
    return Context(profile=profile, identity=identity, spec=spec, days=days,
                   absence_dates=dates, leave_type=leave_type,
                   overrides=overrides, hours=hours, today=today)


def default_outdir(ctx: Context, vault_root: Path | None) -> Path:
    """``classes/admin-forms/records/<first-date>-<form>/`` inside the vault."""
    slug = f"{ctx.absence_dates[0].isoformat()}-{ctx.profile['form']}"
    if ctx.leave_type.get("key"):
        slug += f"-{ctx.leave_type['key']}"
    base = forms_dir(vault_root) / "records" if vault_root else Path.cwd()
    return base / slug


def cmd_render(args) -> int:
    ctx = build_context(args)
    fields = resolve_fields(ctx)
    form_md = render_form(ctx, fields)
    email_md = render_email(ctx, fields)
    record_yaml = render_record(ctx, fields)

    vault_root = Path(args.vault_root) if args.vault_root else None
    outdir = Path(args.out) if args.out else default_outdir(ctx, vault_root)
    if not args.stdout_only:
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "FORM.md").write_text(form_md, encoding="utf-8")
        (outdir / "EMAIL.md").write_text(email_md, encoding="utf-8")
        (outdir / "record.yaml").write_text(record_yaml, encoding="utf-8")

    print(form_md)
    if not args.stdout_only:
        print(f"\n---\nwrote {outdir}/FORM.md, EMAIL.md, record.yaml")
    pending = [f["label"] for f in fields if f["needs_input"]]
    if pending:
        print(f"NOTE: {len(pending)} field(s) still need input: "
              f"{', '.join(pending)}", file=sys.stderr)
    return 0


def cmd_list(args) -> int:
    vault_root = Path(args.vault_root) if args.vault_root else None
    seen: dict[str, Path] = {}
    for path in sorted(BUILTIN_FORMS.glob("*.form.yaml")):
        seen[path.name] = path
    if vault_root and forms_dir(vault_root).is_dir():
        for path in sorted(forms_dir(vault_root).glob("*.form.yaml")):
            seen[path.name] = path            # vault copy shadows built-in
    if not seen:
        print("no form profiles found")
        return 0
    for name, path in sorted(seen.items()):
        profile = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        origin = "vault" if vault_root and forms_dir(vault_root) in path.parents \
            else "built-in"
        print(f"{profile.get('form', name):<24} {profile.get('title', ''):<34} "
              f"[{origin}]")
        for key, meta in (profile.get("leave-types") or {}).items():
            print(f"    --type {key:<20} {(meta or {}).get('label', '')}")
    return 0


def cmd_init(args) -> int:
    """Seed the vault with an identity file and copies of the built-in forms."""
    vault_root = Path(args.vault_root)
    target = forms_dir(vault_root)
    target.mkdir(parents=True, exist_ok=True)
    identity = target / "identity.yaml"
    if identity.exists():
        print(f"kept {identity} (already exists)")
    else:
        identity.write_text(IDENTITY_STUB, encoding="utf-8")
        print(f"wrote {identity}")
    for src in sorted(BUILTIN_FORMS.glob("*.form.yaml")):
        dst = target / src.name
        if dst.exists():
            print(f"kept {dst} (already exists)")
        else:
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"wrote {dst}")
    (target / "records").mkdir(exist_ok=True)
    return 0


IDENTITY_STUB = """\
# Instructor identity for reg-admin-form — the fields every campus form reasks.
# Fill once; every form profile reads from here via `instructor.<key>`.
name: Anthony Giacalone
employee-id:            # CSULB Employee ID (from the paystub / SSO profile)
campus-email: Anthony.Giacalone@csulb.edu
title: Lecturer
department: Computer Engineering and Computer Science
department-code: CECS
college: College of Engineering
chair: Shadnaz Asgari
coordinator: Raquel Porter
associate-dean: Antonella Sciortino
"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="reg-admin-form",
        description="Fill a CSULB administrative form from the vault's records.")
    sub = p.add_subparsers(dest="cmd", required=True)

    lst = sub.add_parser("list", help="list available form profiles")
    lst.add_argument("--vault-root")
    lst.set_defaults(func=cmd_list)

    ini = sub.add_parser("init", help="seed the vault's admin-forms directory")
    ini.add_argument("--vault-root", required=True)
    ini.set_defaults(func=cmd_init)

    ren = sub.add_parser("render", help="render a filled form + email + record")
    ren.add_argument("--form", required=True, help="profile name or path")
    ren.add_argument("--dates", required=True,
                     help="2026-09-10 | 2026-09-10..2026-09-12 | comma list")
    ren.add_argument("--type", help="leave type key (see `list`)")
    ren.add_argument("--term", help="term code, e.g. fa26")
    ren.add_argument("--spec", help="explicit term-spec path")
    ren.add_argument("--vault-root")
    ren.add_argument("--hours", type=float,
                     help="hours to report (default: hours-per-day × days)")
    ren.add_argument("--set", action="append", metavar="KEY=VALUE",
                     help="fill or override a field (repeatable)")
    ren.add_argument("--out", help="output directory")
    ren.add_argument("--stdout-only", action="store_true",
                     help="print the form block; write nothing")
    ren.add_argument("--today", help="override today's date (ISO), for tests")
    ren.set_defaults(func=cmd_render)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except AdminFormError as e:
        print(f"reg-admin-form: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

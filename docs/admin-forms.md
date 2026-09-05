# Filling a campus form without retyping your own schedule

Campus administrative forms have a particular way of wasting your time. There are
no dropdowns, so nothing is picked from a list. They want exact class numbers and
room codes. And they arrive on the mornings you are least able to look any of it
up — the sick day, the day something happened at home.

Every one of those facts is already in the vault. `reg-admin-form` reads them out
and hands you a block you paste into the form, one box at a time.

This walks through a real one: a personal holiday on Thursday, September 10.

## Set up once

```sh
reg-admin-form init --vault-root /mnt/es1/vault
```

That writes `classes/admin-forms/identity.yaml` and copies the built-in form
profiles beside it. Open the identity file and fill in what only you know:

```yaml
name: Anthony Giacalone
employee-id: '012345678'        # from the paystub or the SSO profile
title: Lecturer
department: Computer Engineering and Computer Science
college: College of Engineering
```

Every form profile reads from here, so an employee ID gets typed once rather than
once per absence.

## Tell the term-spec which days campus is closed

The tool works out which classes an absence costs by expanding your sections'
meeting patterns across the dates. That answer is wrong unless it also knows the
days nothing meets. Add them to the term-spec:

```yaml
no-instruction:
  - { date: 2026-09-07, label: "Labor Day (campus closed)" }
  - { date: 2026-11-11, label: "Veterans Day (campus closed)" }
  - { start: 2026-11-23, end: 2026-11-25, label: "Fall Break (no classes, campus open)" }
  - { start: 2026-11-26, end: 2026-11-29, label: "Thanksgiving Holiday (campus closed)" }
```

Copy them from `notes/csulb-deadlines-<AY>.md` at the start of the term.

> [!WARNING]
> Skip this and a Thanksgiving-week absence will bill you for three classes that
> were never going to meet.

## Render it

```sh
reg-admin-form render \
    --form notice-of-absence --type personal-holiday \
    --dates 2026-09-10 --term fa26 --vault-root /mnt/es1/vault
```

Three files land in
`classes/admin-forms/records/2026-09-10-notice-of-absence-personal-holiday/`:

| File | What you do with it |
|---|---|
| `FORM.md` | Paste into DocuSign, box by box. Every value is in its own fenced block. |
| `EMAIL.md` | The heads-up to the timekeeper, To/Cc already right. |
| `record.yaml` | Nothing, today. It is how you answer "have I used my personal day this year?" in March. |

The supporting table is the part the form actually wants:

| Date | Course | Class # | Time | Room | Topic scheduled |
| --- | --- | --- | --- | --- | --- |
| 2026-09-10 (Thu) | CECS 378 §01 | 4785 | 11:00-12:15 | VEC-331 | Symmetric and Asymmetric Encryption |
| 2026-09-10 (Thu) | CECS 326 §03 | 10674 | 15:30-16:45 | DESN-112 | Processes and Threads, ctd |
| 2026-09-10 (Thu) | CECS 326 §01 | 1131 | 17:30-18:45 | DESN-112 | Processes and Threads, ctd |

Topics come from each section's syllabus *Week of* table, so the form says what
was going to be taught, not just that a class existed.

## Filling the boxes only you can answer

`FORM.md` opens with a list of what is still blank. Usually that is the coverage
plan. Supply it inline:

```sh
reg-admin-form render --form notice-of-absence --type personal-holiday \
    --dates 2026-09-10 --term fa26 --vault-root /mnt/es1/vault \
    --set coverage="All three sections meet asynchronously; Canvas modules posted in advance."
```

`--set` fills any field by key. Re-rendering overwrites the record, so iterate
freely until it reads right.

## Dates

- One day: `--dates 2026-09-10`
- A span: `--dates 2026-09-10..2026-09-12`
- Scattered days: `--dates 2026-09-10,2026-09-17`

Hours default to eight per absence day. Override with `--hours 4` for a half day.
The form reports scheduled contact hours separately, because those are a different
number (three sections on one Thursday is 3.75 contact hours against 8 charged),
and timekeepers differ on which they want.

## What the personal holiday does not ask you

A personal holiday is contractual. You are not applying for it, so the profile
drops the justification field entirely and says so in the rendered form. If
DocuSign insists on a box, "Personal holiday" is a complete answer. Nobody is
owed the reason.

Sick leave and bereavement keep the field, because those forms do ask.

## Adding another form

Copy a profile in `classes/admin-forms/`, change the fields, done — no Python.
A field's `source:` is a dotted expression:

| Source | Gives you |
|---|---|
| `instructor.name`, `instructor.employee-id` | anything in `identity.yaml` |
| `absence.dates`, `absence.day-count`, `absence.hours`, `absence.contact-hours` | the absence itself |
| `classes.lines`, `classes.table`, `classes.sections`, `classes.skipped` | the affected meetings |
| `leave.label`, `term.term-name`, `today.long` | context |
| `literal:someone@csulb.edu` | a fixed value |
| `prompt` | you, via `--set` |

A leave type can carry `omit:` to drop fields it isn't owed, `defaults:` to
prefill one, and `guidance:` to print a note at the top of the form.

## See also

- `SKILL.md` — the `/timeoff` verb and the full source reference
- `lectern/class_calendar.py` — meeting-pattern expansion, if a `meets` string
  ever parses wrong

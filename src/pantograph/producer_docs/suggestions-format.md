# `collaboratorium-suggestions/0.3`

The file an external tool writes and a person uploads. This page is the
specification: a producer should be able to work from it and the `contract.json`
in a handoff bundle alone.

Write records in the voice the [record style guide](record-style-guide.md)
describes. This page says what the shape is; that one says what good content is.

---

## 0. The three rules that are not negotiable

**Nothing in this file becomes a record.** Every value arrives marked as not
yet stood behind, and a person confirms it field by field before anything is
saved. A proposal is a draft for someone else to sign, so flag what you guessed:
an uncertainty you declared costs a reader a glance, and one you hid costs them
their confidence in the whole file.

**Never predict an id.** Ids are allocated on save. Records in this file refer
to each other by `key` or by name.

**An update never removes anything.** On a record that already exists, a link
list is added to and never replaced, because someone else's link is not yours to
delete. Removing a link is a thing a person does in the app, deliberately.

---

## 1. Shape

```yaml
format: collaboratorium-suggestions/0.3
contract: sha256:97088fd8486f…        # from contract.json; a mismatch warns
producer:
  name: my-scanner
  run_id: run-2026-11-04-a           # becomes the provenance origin
subject: Gabe Bolton                 # whose work this is; must name a person
period: {from: 2026-05-29, to: 2026-11-04}

coverage:                            # where your evidence actually stops
  - source: WorkLog/idems.yaml
    through: 2026-08-06
    note: >-                         # why it stops, and what is lost with it
      No narrative log after this date, so later records rest on code hosting
      alone and the split of effort between strands is not recoverable.
  - source: github:IDEMSInternational
    through: 2026-11-04

sources:                             # what you read, referenced by `cites`
  - id: ar2021
    kind: document
    ref: IDEMS International Annual Report 2021.docx

initiatives:
  - key: iogt
    name: Development of the Internet of Good Things
    description: >-
      A set of websites making life-saving information available for free on
      low-end devices in over eighty countries.
    status: active
    responsible_person: Gabe Bolton
    parent_initiatives: [Parenting for Lifelong Health Digital]
    source_ref: github:IDEMSInternational/iogt
    cites: [ar2021]
    inferred:
      parent_initiatives: grouped under PLH in the report, never stated outright

activities:
  - name: Development of Internet of Good Things version 2 for UNICEF
    description: >-
      The major focus of the year for many in the team.
    attachments:
      - name: Version 2 release notes
        url: https://github.com/IDEMSInternational/iogt/releases/tag/v2
    start_date: 2021-01-01
    end_date: 2021-12-31
    initiatives: [iogt]             # a key in this file, or an existing name
    people: [Gabe Bolton]
    status: active
    source_ref: github:IDEMSInternational/iogt#v2
    cites: [ar2021]
    inferred:
      start_date: '"this year", no month given'
      end_date: '"this year", no month given'

contracts: []
```

Three record lists, one per table a proposal may target: `initiatives`,
`activities`, `contracts`. Everything else — people, organisations — is referred
to, never created. An identity is something a person establishes.

**Attachments.** An activity's `description` (also written `summary`) and its
`attachments` are two fields of the same block. Attachments are the evidence a
reader would want to open: the release, the pull request, the document, the
recording. Give each as `name` and an `http(s)` `url`; a row with no address is
dropped with a warning. Propose them wherever you cited a page or a file for the
activity, and leave them out only when there is nothing to open. On an activity
that already has attachments yours are **added to** the list, never replacing it,
and a link already there is not repeated.

## 2. Values are plain

A value is a scalar or a list, written the way you would write it in the form.
No wrapper, no confidence object around each one.

This is deliberate, and it is the one place this format departs from its
predecessor. A per-value block carrying `value`, `confidence`,
`confidence_main`, `confidence_review` and three kinds of note turns a
fifty-record file into something no one reads to the end — and a file no one
reads is a file whose errors reach the register. The reviewer is the point of
the whole mechanism, so the common case stays legible and uncertainty pays for
its own syntax.

## 3. `inferred:` is how you flag a guess

One optional map per record, element name to the reason:

```yaml
    start_date: 2021-10-01
    location: United Kingdom
    inferred:
      start_date: '"towards the end of the year", no month given'
      location: '"a community centre in the UK" — country only'
```

An element **absent** from `inferred:` is a claim that you read it from the
source, more or less verbatim. An element **present** is a claim that you worked
it out, and the string says how. Both are recorded: an inferred value is stored
with a lower confidence and your reason as its note, and a reader sees the
reason next to the field when they confirm it.

You may also write ordinary YAML trailing comments — `# inferred` after a value
reads nicely and several producers do it. They are *not* read: comments do not
survive parsing, so a reason that exists only in a comment reaches nobody. Put
it in `inferred:` and comment as well if you like.

**Quote a reason that contains punctuation.** A plain YAML value that starts
with a quotation mark and then carries on is a syntax error, and one such line
makes the whole file unreadable: the import refuses it and names the line, and
nothing is staged. A reason like `"commissioned by NFPB" is read from the
wording` must be written `'"commissioned by NFPB" is read from the wording'`.
Wrap every `inferred:` reason, and any value containing `: ` or ` #`, in single
quotes or use a folded `>-` block. If you can run any language with a YAML
parser, parse the file before you hand it over.

Getting this wrong in the generous direction is cheap and in the mean direction
is not. An inferred value you declared is a field someone glances at; one you
did not is a guess that enters the record as a reading.

## 4. Linking

| On | Written as | Means |
| --- | --- | --- |
| an activity | `initiatives: [name or key]` | which strands of work it belongs to |
| an activity | `people: [name]` | who did it |
| an activity | `parent_activities: [name or key]` | nesting |
| an initiative | `parent_initiatives: [name or key]` | nesting |
| an initiative | `responsible_person: name` | one person, who owns it |
| a contract | `initiatives:`, `activities:`, `organisation:` | as the form has them |

A name must match an existing record exactly, or be a `key` defined in this
file. The import resolves both and refuses a name that is neither, naming it —
so a typo in a link is caught rather than silently creating something.

An activity needs **at least one initiative and at least one person**. That is
the form's rule, not this format's.

## 5. Updating something that exists

Give a `target`:

```yaml
initiatives:
  - target: {id: 141, expect: anastom}
    description: >-
      A framework for turning heterogeneous open resources into validated,
      schema-conformant output.
    inferred:
      description: drafted from the repository README
```

`expect` is the record's current name. If the id and the name disagree the
import refuses the record, so a stale id edits nothing.

On an update: link lists are **added to**, scalar values are proposed as
changes, and nothing is ever removed. A scalar that would overwrite an existing
non-empty value is flagged for the reviewer rather than applied quietly.

## 6. Identity, and why `source_ref` matters

```yaml
    source_ref: github:IDEMSInternational/iogt#v2
```

A stable external name for the *evidence* this record came from. Rules:

- **Anchor it on the thing, never on the run.** `gabe/2026-11-04/iogt-v2`
  embeds the date you looked, so next month's run proposes the same work under a
  new ref. Then re-importing duplicates everything and no decline is remembered.
- The import deduplicates on it. Running your producer twice over unchanged
  evidence must produce an identical set of refs, and the second import must
  therefore change nothing.
- A record a person **declined** is remembered by it, and comes back in
  `rejections.yaml` in the next bundle. Propose it again and it is dropped,
  not re-queued.

`source_ref` is optional. Without one a record cannot be deduplicated or
declined durably, so the import warns and treats it as new every time.

## 7. When several people did the same work

This is the normal case, not an edge case, and the format handles it by being
honest rather than clever.

If you and a colleague both worked on the second African STACK conference, both
of your producers will propose it — from different evidence, so with different
`source_ref`s. Dedupe cannot see that they are the same thing. What happens:

- The import matches your proposed name against **what is live now** and against
  **other people's pending suggestions**, not against the snapshot in your
  bundle, which may be hours old. A likely match is flagged with what it
  matched.
- Where the match is a record that already exists, the right resolution is
  almost always an **update that adds you to it** rather than a second record.
  The reviewer is offered exactly that, and link lists being add-only is what
  makes it safe.
- Where the match is someone else's pending suggestion, the two are **grouped**.
  A reviewer sees both descriptions together, keeps one, and both of you end up
  linked to the surviving record.

What you can do to help: prefer `target:` over a `create` whenever the snapshot
already has the thing, keep names in the source's own words rather than your
own phrasing of them, and link generously — `people:` with one name is what
tells the resolution which contributions to merge.

What you should not do: leave your colleague off a record because you are not
sure how to express joint work. An activity with one person named and a flagged
inference is better than one person's private copy of a shared thing.

## 8. Tags

Written by category and term name, like a link and for the same reason — it is
what a reviewer can read:

```yaml
    tags:
      impact_area: [Education, Data Science]
      idems_domain: [IDEMS R&D]
```

The terms are **data, not config**, so this page does not list them and the
contract cannot either. `contract.json` says where they live —
`subform.vocabulary.resolved_in: snapshot` — and the terms themselves are in
`snapshot.yaml`, under the rows of the table that vocabulary names. Read them
from there, every run, because a term added this morning is proposable this
afternoon and a list copied into a producer goes stale silently.

Each row's `key_values` names its categories; each category names its terms as
`{key: label}`. Write the label; the import matches without case or
punctuation and stores the key.

Three rules the import enforces:

- **A term must be in the vocabulary.** An invented one is refused, and the
  message names the category's real terms. Multi-word near-misses are offered
  back; a single-word typo currently is not, because the matcher refuses fuzzy
  matching on one-word names — that is what stops it confusing two genuinely
  different products whose names differ by a letter.
- **A category may refuse proposals.** One carrying `"producer": false` in its
  `key_values` is dropped with the reason that row gives. Its terms are ones a
  person is expected to choose.
- **Too many is reported, never refused.** See the style guide for the number
  and why it is guidance.

What the terms *mean* is in the [record style guide](record-style-guide.md),
which carries the definitions. Choose from those rather than from the labels:
several terms read obviously and are not, and the labels alone are what made an
earlier attempt at mapping historical values fail.

## 8.1 What is refused outright

Read `contract.json`: an element with `accepts_suggestions: false` is refused
and the reason is given there. In this deployment that is `people.email`. A tag
category is refused only if the vocabulary marks it so (above); the strategic
category is currently open to proposals, which should be declared as guesses.

## 9. Before you hand it over

Check, in this order:

1. Every element you set exists in `contract.json` for that table.
2. Every required element is present: `name` plus `responsible_person` on an
   initiative, `name` plus one initiative and one person on an activity.
3. Every name in a link resolves — to a `key` in this file or to a record in
   `snapshot.yaml`.
4. Every `target.id` exists in the snapshot and its name matches `expect`.
5. Dates parse, and no `end_date` precedes its `start_date`.
6. Every name you would create is not already in the snapshot under a
   different phrasing. This is the check producers skip and reviewers pay for.
7. `coverage` says where your evidence genuinely stops, with the *why* in each
   entry's `note` — see below.

## 10. `coverage`, and where the explanation goes

One entry per source, each with `source`, `through`, and an optional `note`
saying why it stops and what is lost with it. Only an entry whose `through`
falls before the end of `period` is reported to the reviewer, so listing a
source that ran to the last day is free and worth doing — it says what you
looked at.

**Put the explanation in `note`, not in a YAML comment beside it.** Comments do
not survive parsing, so a caveat written as a comment reaches nobody. This is
the mistake the first real file through here made: four paragraphs of genuinely
useful qualifications — an unauthenticated forge, Drive revision histories not
read, a personal repository deliberately excluded — all of it invisible to the
import and to the person reviewing it.

The import runs all of this and names what failed, before anything is staged.
Finding it here costs nobody else's time.

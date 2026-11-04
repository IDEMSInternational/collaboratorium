# Agentic additions: a handoff page out, a suggestions file in

How a person gets Collaboratorium's shape and contents into a local agent, has
that agent propose records from evidence the deployment cannot see — repo
activity, Drive activity, notes — and gets the reviewed proposal back in.

Read with [provenance.md](provenance.md) (the mechanism the import lands on),
[roadmap.md](roadmap.md) §11–§14 (the same problem, scoped to the GDPR
register), and `anastom`'s `docs/activity_report_ingestion_spec.md`, which is a
much longer design for the producer half and the reason several decisions below
are already made rather than open.

Status: design, nothing implemented. The work items in §7 are written to drop
into GitHub issues.

---

## 0. Summary

- The roadmap already contains this feature, as items **11 (export the producer
  contract)**, **12 (ingest suggestions)** and **13 (suggested-vs-confirmed
  state)**. 13 shipped as #97 — provenance exists, stores, renders amber,
  blocks `required:` until confirmed. 11 and 12 do not exist in any form:
  there is no `grep` hit for a contract, a hash, a suggestion or a
  `source_ref` anywhere in `src/`.
- So this is not new work to invent. It is **items 11 and 12, pulled out from
  under the GDPR plugin and scoped to Collaboratorium's own tables**, which is
  where the evidence is already sitting and where the manual run has already
  been done once.
- **The wire format exists.** `anastom`'s spec describes
  `collaboratorium-suggestions/0.1` as actually produced by a Claude Code
  session on 2026-09-14 — 47 records against the live schema — and
  `0.2` as the corrected format. We should adopt 0.2 rather than invent a
  third thing, and publish its schema from this repository, since this is the
  consuming end.
- **Do not write records on import.** Roadmap #69's first rule is "suggestions
  are never records", and the code enforces it from the other direction: a save
  carrying an unconfirmed answer to a required question is *refused*
  (`requirements.rejection_message`, called in `form_gen.handle_submit`). An
  import that inserted an activity with a suggested `name` would write a row
  the form engine itself would not have accepted. Suggestions stage; a human
  confirms; the confirmation is what writes.
- **The review step should be the existing editor, prefilled.** `provenance.md`
  states the seam outright: *"a page that wants to open a prefilled form — a
  scope inheriting from its parent, an ingested suggestions file — needs no
  change in core."* `generate_form_layout` already takes `initial_values` and
  `provenances`. Import therefore needs **no new write path into the record
  tables at all**, which is what makes a v1 small.
- **`anastom` is the right design partner and the wrong v1 runtime** (§6). Its
  spec is the best document either repo has on this problem. Its
  implementation is a spike that does not exist, behind funding-gated
  milestones, and its model calls go through a paid provider key — the thing
  worth avoiding when a Claude Code subscription already drives the loop.

---

## 1. What the person actually does

The envisaged loop, with the pieces named:

1. Signs in to Collaboratorium, opens **Handoff**, clicks one download and
   copies one line of text.
2. Drops both into a local Claude Code session. The session reads the schema
   instructions, reads the snapshot so it knows what already exists, scans the
   repos and Drive folders it has access to, and writes a YAML suggestions
   file.
3. Reads the YAML. Renames things, promotes an activity to an initiative,
   re-parents, deletes records it does not want. This is where almost all the
   value is added — see §3.
4. Back in Collaboratorium, opens **Import**, pastes the YAML, and gets a
   validation report before anything is staged.
5. Walks the staged queue. Each item opens the normal editor with its values
   prefilled and marked suggested. Confirming the fields saves a normal record.

Steps 1 and 4–5 are this repository's work. Step 2 is a producer, which by
roadmap #71's rule lives outside this repository and never imports core. Step 3
is a text editor for now, and a review tool later.

---

## 2. Out: the handoff page

### 2.1 What an agent needs, and what it should not have to guess

Four things, and the page's whole job is that none of them has to be
reconstructed by hand:

| Artefact | Why it cannot be hand-maintained |
| --- | --- |
| `contract.json` | The element names, types, required/relevant conditions and choice lists *are* `config/`. A document restating them drifts within two sprints. Roadmap #11's rule: derived, never hand-written, and it carries the hash of the config it came from. |
| `snapshot.yaml` | A proposal has to link to records that already exist, must not duplicate the 92 initiatives already in there, and must not re-propose what was rejected last time. All three need current state, not just schema. |
| `instructions.md` | How to read the contract, how to write the format, what the review conventions are. Versioned in git, **pointed at** by the page rather than copied into it. |
| `rejections.yaml` | Roadmap #69's fourth rule — "rejection is sticky". A suggestion a human declined must not come back next run. Either we export rejections or the producer keeps them; exporting is the only option that survives the producer being replaced. |

### 2.2 Not the raw `.db`, and not instead of it

`/admin/maintenance?action=download` already serves a `VACUUM INTO` snapshot of
`database.db`, and an agent can read SQLite perfectly well, so the temptation is
to call the feature done. Three reasons not to:

- It is **admin-only** (`ADMIN_EMAILS`), and the point is that any signed-in
  contributor can hand their own activity to an agent.
- The tables are **append-only on `(id, version)`** with `status='deleted'`
  tombstones in the link tables. Every reader has to reimplement
  `ROW_NUMBER() OVER (PARTITION BY id ORDER BY version DESC)` and the
  not-deleted filter correctly, and a producer that gets it subtly wrong
  proposes links against superseded rows. Core already has this right in
  `db.get_latest_record` and `db.get_relation_links`; the snapshot should be
  its output, not an invitation to redo it.
- It carries **no contract and no hash**, so nothing ties a proposal to the
  config it was drafted against.

Keep the `.db` download where it is, as the backup tool it is. The handoff page
is a different artefact for a different reader.

### 2.3 One bundle, one line to copy

The instinct to put copy-pasteable schema instructions on the page is right
about the goal and wrong about the mechanism: a blob large enough to describe
this schema is large enough to go stale on the page, and a human pasting it is
a human who can paste half of it.

Instead: the page offers **one** download,
`collaboratorium-handoff-<short-hash>.zip`, holding the four files above, and
**one** copyable line naming the bundle and the pinned instructions URL —
something a session can be started with directly. The instructions file in the
bundle is the authority; the URL is the pointer for an agent that wants the
latest. Both carry the config hash, so a proposal drafted against last
quarter's choice lists is detectable rather than mysterious.

### 2.4 The decision this page needs taken first

`snapshot.yaml` is a **bulk export of personal data** — `people.name`,
`people.email`, who worked on what, when. Today the only bulk export is
admin-gated for exactly that reason. `docs/data-protection-model.md` is the
frame, and this is a lawful-basis question, not a UX one.

The narrowest thing that still works: `contract.json` to any signed-in user
(it holds no records); `snapshot.yaml` to any signed-in user but with
`people.email` omitted, since a producer needs to *resolve* a person, which a
name and an id do, not contact them. Full export stays admin. This needs
writing down and agreeing, not assuming.

---

## 3. The format, and why YAML

YAML, and not because it is tidier. The format's leading block carries a
**review queue** — every value below the confidence threshold, lowest first,
with the reviewer's note — and the per-value notes explaining why a date was
guessed. Those are comments. JSON cannot hold them, so a JSON format forces the
explanations into data fields, where they are read by the importer that does not
want them and missed by the human who does.

Adopt **`collaboratorium-suggestions/0.2`** as specified in `anastom`'s
`docs/activity_report_ingestion_spec.md` §3.7. Its shape, and why each part is
there:

- **`key`** — a local handle. New records must link to each other before they
  have ids, and they must never *predict* ids: `forms.yaml` declares a `uuid`
  id strategy but the save path allocates `max(id) + 1`
  (`form_gen.py:451`). A proposal that guesses 154 and gets 157 is corrupt.
- **`source_ref`** — stable external identity, so re-running the producer is
  idempotent and so a rejection can stick to something. The manual run got this
  wrong by embedding the run date; the fix is to anchor on the evidence (a repo
  URL, a document id), not on when it was looked at.
- **`action: create | update`**, with `target: {id, expect}` on an update.
  `expect` is the record's current name: a wrong id then fails validation
  instead of quietly editing a different record.
- **`table`**, **`values`** keyed by form element name, each leaf a node
  carrying `value`, `confidence`, and the notes.
- **`placement`** — the record's *kind* and its *parents*, scored
  independently. This is the one piece worth insisting on, for the reason in
  §3.1.
- **`evidence`** — ids into the producer's own bundle, not prose. Evidence is
  never stored in Collaboratorium (`provenance.md`), so prose in the upload is
  note text leaking into the register for no benefit.

### 3.1 The corrections are structural, so score the structure

The single most useful finding in the manual run: of the human's corrections,
essentially none was "this value is wrong". They were rename, split, promote an
activity to an initiative, re-parent, change owner — *this item is the wrong
kind, in the wrong place, at the wrong granularity.*

A format that only scores values has nowhere to put a doubt about placement,
and a review pass that can only score values strands its structural objections
in free text on individual leaves. Hence `placement` as a scored block with its
own review item. Link values in `values` are then generated from it.

This also sets the ceiling on what the *in-app* import can do. Promoting an
activity to an initiative is not an edit to a field — initiatives have no dates
and no attachments, activities do — so it cannot be expressed by confirming or
editing values in a Collaboratorium form. Structural review happens in the
producer, before upload. The import page's job is to make that boundary
obvious rather than to pretend it can be crossed.

---

## 4. In: validate, stage, confirm

### 4.1 Validation runs before anything is staged

The import page accepts a paste or a file, and its first and most valuable
output is a report. The rules, mostly ported from what the manual run's
throwaway script already did:

1. Every `target.id` exists and its name matches `expect`.
2. Every `key` referenced is defined in the file; no cycles in `placement`.
3. Required elements are present per `config/forms.yaml` — `name` and
   `responsible_person` for an initiative; `name`, at least one
   `initiatives_links` and at least one `people_links` for an activity.
4. Dates parse, and `end_date` is not before `start_date`.
5. Choice values are in vocabulary. Note the trap: **only `status` has its
   choices in config.** Every other `select_one` / `select_multiple` reads
   `parameters.source_table`, so the vocabulary is in the database. Validating
   links means validating against the snapshot as well as the contract hash —
   the contract alone cannot do it.
6. A contract-hash mismatch **warns**, naming what changed, rather than
   refusing. A proposal drafted on Monday against a config edited on Tuesday is
   usually still good.
7. Near-duplicate names against existing records are surfaced, because TODO
   item E is still an open policy question and 92 initiatives are already in
   there. Surfaced, not blocked: "Weekly standup" is a legitimate repeat.
8. Coverage gaps the producer declared are shown, not buried. The manual run's
   notes evidence stopped five weeks before the period ended and nothing in the
   file said so.

### 4.2 Staging, and what the staging table is for

A `suggestions` table, created by core on every start as `provenance` is, one
row per proposed record with its parsed values, its `source_ref`, its run id
and its state (`pending | accepted | rejected`). It exists to satisfy exactly
two requirements that nothing else can: re-importing the same file produces the
same state, and a rejection is remembered by `source_ref` so the next run can
be told about it.

It is deliberately *not* a shadow copy of the schema. It holds the proposal as
submitted; the accepted record is written by the normal path.

### 4.3 Confirming is the write

Each pending item opens `activities_form` or `initiatives_form` through the
existing editor, with `initial_values` from the proposal and a `provenances`
map marking every value `suggested`, `origin` = the producer's run id,
`confidence` from the leaf. From there the machinery that shipped in #97 does
the work with no changes: unconfirmed values render amber and dashed, they do
not satisfy `required:`, the disabled submit button says *"Add Name and confirm
Collection Purpose to submit"*, and a save that slips an unconfirmed required
answer past the button is refused.

The honest cost: that is one form per record, and the manual run produced 47.
Per-field confirmation is a rule, not an oversight — `provenance.md` is explicit
that a "confirm everything" button would be the fastest way to make the
mechanism meaningless — so the throughput problem cannot be solved by batching
signatures. It has to be solved by making the queue fast to move through, and
by the producer sending fewer, better records. Worth measuring early: how many
records a person will actually accept in one sitting is the number that decides
whether this feature is used.

Two consequences to accept rather than engineer around:

- **A subform's fields cannot carry provenance** (`provenance.md`, "Limits").
  The activity `description` *is* a subform — `{"1": {description,
  attachments}}` in `config/forms.yaml` — so the summary of an imported
  activity has nowhere to land its confidence today. Activities are the sparse
  and valuable table, so this is the most load-bearing limit in the whole
  design, and it is a core form question rather than an import one.
- **Producer-side review is not register confirmation.** A value the human
  settled in chat with the agent carries `reviewed: {by, at}` in the file. It
  must not be translated into `confirmed_by`. A signature means someone read
  that value *here*; the moment an upload can assert one, the register stops
  being defensible. Leave it as an explicit open question and default to no.

---

## 5. Where this leaves the GDPR roadmap

Items 11 and 12 are listed under "The producer interface and the LLM pipeline"
and were scoped for the register. Building them for Collaboratorium's own
tables first is strictly better for both:

- The contract exporter reads the merged config and knows nothing about which
  tables it describes, so it serves the register unchanged.
- Ingest and staging are table-agnostic for the same reason.
- Collaboratorium has **real evidence and a real user** — repo history, Drive,
  a person who wants their quarter's work recorded — where the register has a
  codebase scanner that does not exist yet. The failure modes get found by use.
- The order in the roadmap's diagram (`11 → 12 → 13`) already has 13 shipped out
  of sequence, so the dependency chain is not binding.

The one thing that genuinely wants the register's framing is item 14's static
analysis. That stays where it is.

---

## 6. `anastom`: borrow the design, not the runtime

**It has thought about this harder than we have.** `anastom`'s
`docs/activity_report_ingestion_spec.md` (2026-09-14, ~1,260 lines) is a design
for precisely this pipeline: the format, a validator rule set, a review model
built around structural ops, an orchestration recommendation, and a list of
nine places `anastom`'s own abstractions break under the use case. It is
grounded in a real run against this schema — 47 records, 22 repos, ~859 commit
lines, a 1,067-entry time log, and a human's corrections recorded as a table.
Nothing in this document should be designed without reading it, and §3 and §4
above are largely its conclusions restated from the consuming end.

**It is not something to depend on for v1.** Its own spec says so: the work is
"exploratory… **not** a roadmap milestone task", and the milestones that would
own the framework changes it needs (M2.5 review client, M3 heterogeneous
ingestion, M7 second target) are all funding-gated. The
`anastom_collaboratorium` plugin does not exist. And the parts that *do* exist
assume a provider API key through `inferenceswitch`, which is the cost the
subscription-driven loop is there to avoid — `--offline` substitutes the model
call and nothing else, which is fine for StoryMap chapter titles and useless
here, where the model call is the entire job.

**So, for v1, the producer is a skill in this repository.** A
`.claude/skills/propose-records/` that a local Claude Code session runs: read
the handoff bundle, sweep the repos and Drive folders, cluster, place, draft,
self-review, emit `collaboratorium-suggestions/0.2`. It runs on the
subscription, it has no API key, and it is version-controlled next to the
contract it targets. The genuinely deterministic parts of `anastom`'s spec —
the validator, the blind second pass, `confidence = min(main, review)`, the
run ledger — are worth lifting as a small standalone script, because that
script is exactly the thing to hand over when `anastom` is funded to take this
on.

**What "reaching out" should concretely mean:**

- A decision issue on `anastom`'s tracker asking whether Phase 1 of
  `anastom_collaboratorium` can be claimed, and if not, confirming that this
  repository may ship a subscription-driven producer against the same format
  without forking it.
- Agreement that **this repository owns `collaboratorium-suggestions`** and
  publishes its schema, since it is the consumer and the only place the
  contract hash can be authoritative.
- The Q3 manual run frozen as a fixture — the main file, the blind review file,
  the human-corrected final file — so both repositories score against the same
  baseline. That fixture holds personal notes, so it is private, which is
  already `anastom`'s Phase 0 plan.

---

## 7. Work items

Written to drop into issues. Nothing here is started.

### A. Decide the handoff page's data-protection posture

**Labels:** discussion, security, data-protection

Who may download a bulk snapshot of people and their work, and does it include
`people.email`? Today the only bulk export is admin-gated. §2.4 proposes
contract to any signed-in user, snapshot to any signed-in user without emails,
full export admin-only. Settle before A2, because it determines what the
endpoint serves to whom.

**Acceptance:** a written decision in `docs/data-protection-model.md`, and the
handoff endpoint's gating follows from it.

### B. `pantograph export-contract`

**Labels:** feature, core, integration

Roadmap item 11, built generally rather than for the register. A CLI emitting a
JSON Schema projection of the merged config — tables, element names, types,
choice lists, `required:` and `relevant:` conditions — carrying a hash of the
config it came from. Note that `python -m pantograph` currently has no
subcommands at all, so this introduces the CLI surface.

Choice lists sourced from `parameters.source_table` must be *declared as such*
rather than resolved, since they are data and not config.

**Acceptance:** `pantograph export-contract` writes a schema an external tool
validates against; editing an element's choice list changes the schema and its
hash; a config with no Explore plugin exports without error.

### C. The handoff page and bundle

**Labels:** feature, integration
**Depends on:** A, B

A `login_required` page offering one zip — `contract.json`, `snapshot.yaml`,
`instructions.md`, `rejections.yaml` — and one copyable launch line. The
snapshot is built from `db.get_latest_record` and `db.get_relation_links` so
that latest-version and tombstone handling is core's, not the reader's.

**Acceptance:** a signed-in user gets a bundle whose contract hash matches the
running config; the snapshot contains no superseded versions and no deleted
links; nothing on the page restates the schema in prose.

### D. Publish the `collaboratorium-suggestions/0.2` schema

**Labels:** docs, integration

Adopt `anastom`'s §3.7 format, document it in this repository as the consuming
end, and ship a machine-readable schema for it in the bundle. Includes the
`source_ref` anchoring rule, since the manual run's run-date-based refs break
idempotency and sticky rejection on the second run.

**Acceptance:** a written spec and schema; the manual run's corrected file
validates against it; two runs over unchanged inputs produce identical
`source_ref`s.

### E. Validate and stage an uploaded suggestions file

**Labels:** feature, core, integration
**Depends on:** C, D

Roadmap item 12. Paste-or-upload, validate per §4.1 with every failure naming
the record and the element, then stage into a `suggestions` table keyed on
`source_ref`. No record tables are written.

**Acceptance:** importing the same file twice produces the same state; an
out-of-vocabulary value is rejected naming the element and the allowed values;
a contract-hash mismatch warns rather than refusing; a rejected `source_ref`
appears in the next export's `rejections.yaml` and is not re-staged.

### F. The review queue: open each suggestion as a prefilled form

**Labels:** feature, forms, ux
**Depends on:** E

A page listing pending suggestions that opens each in the existing editor with
`initial_values` and `provenances` set, using the seam `provenance.md` already
documents. Accepting is the normal save; declining writes the rejection.

**Acceptance:** a staged activity opens prefilled with every value amber and
unconfirmed; confirming the required fields saves a normal record whose
provenance rows carry the producer's run id; declining is remembered by
`source_ref`.

### G. Provenance for subform fields

**Labels:** enhancement, forms, core

The activity `description` is a subform, so it cannot carry provenance
(`provenance.md`, "Limits") — the same limit `relevant:` has. Activities are
the table an import is for, and the summary is the field a model is most useful
at drafting, so this is the design's tightest constraint.

Either lift the limit, or decide that an imported activity's summary arrives
unmarked and say so loudly, which is the claim the whole mechanism exists to
prevent making by accident.

**Acceptance:** a decision; if lifted, a subform leaf renders and stores
provenance like any other element.

### H. A producer skill in this repository

**Labels:** feature, integration
**Depends on:** C, D

`.claude/skills/propose-records/`: read the bundle, sweep repos and configured
Drive folders, cluster into work items, place them against the existing
hierarchy, draft, run a blind second pass, emit 0.2 with
`confidence = min(main, review)` and a declared coverage window. Plus the
standalone validate/blind/merge script, which is the deterministic core and the
handover artefact for `anastom`.

**Acceptance:** run against a repo set, the skill emits a file that E imports
with no manual editing; the coverage window names the last date each evidence
source covers.

### I. Extract the save path from the submit callback

**Labels:** refactor, core
**Depends on:** nothing; unblocks a programmatic writer

Not needed for A–H, and listed so it is not mistaken for a prerequisite.
Roughly 230 lines of record and link-table write logic live inside the
`handle_submit` closure in `form_gen.py` — column mapping, Dash value
normalisation, append-only versioning, link add/tombstone, provenance save,
relevance nulling, the requirements refusal. Nothing outside a Dash callback
can write a record today.

The design above avoids needing this by making confirmation the write. Anything
that later wants a non-interactive writer — a migration, a bulk accept, a test
fixture — needs it first.

**Acceptance:** a plain function saves a record with its links and provenance;
`handle_submit` calls it; the existing tests pass unchanged.

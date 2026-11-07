# Agentic additions: a handoff page out, a suggestions file in

How a person gets Collaboratorium's shape and contents into a local agent, has
that agent propose records from evidence the deployment cannot see — repo
activity, Drive activity, notes — and gets the reviewed proposal back in.

Read with [provenance.md](provenance.md) (the mechanism the import lands on),
[roadmap.md](roadmap.md) §11–§14 (the same problem, scoped to the GDPR
register), and `anastom`'s `docs/activity_report_ingestion_spec.md`, which is a
much longer design for the producer half and the reason several decisions below
are already made rather than open.

Status: the way **out** is built — the contract exporter (item B) and the
handoff page and bundle (item C). Nothing of the way **in** exists yet: no
format schema, no validation, no staging, no review queue. The four decisions
the design needed are settled, in "Decisions taken" below. The remaining work
items in §7 are written to drop into GitHub issues.

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

## Decisions taken

Settled 2026-11-04, before any code. Each is recorded where it bites, below;
gathered here so the import's shape can be read without the reasoning.

**The bundle goes to any signed-in user, without `people.email`.** Access is
already restricted to `@idems.international` (`auth.py:136`) and the Explore
spreadsheet already renders a grid column for every column of every node table,
`people.email` included (`tab_spreadsheet.py:150`), so gating the bundle by
role protects nothing a user cannot already read in the app. The real novelty
is bulk egress onto a laptop and into a model's context, and the answer to that
is to send less, not to send it to fewer people. A producer needs to *resolve* a
person — a name and an id do that — not to contact one. The `.db` download stays
admin-only. See §2.4.

**Provenance lands at element level, not per leaf.** The whole `description`
subform carries one suggested provenance. Per-leaf confidence is deferred, not
designed out. See §4.3 and item G.

**Duplicate detection is a non-blocking similarity advisory.** There are no
duplicated names in the live data at all, so an exact-name check would catch
nothing; the real failure is a differently-worded record for work already
recorded. This leaves TODO item E's general policy question untouched. See
§4.1 rule 7.

**A suggestions file may not set `tag_groups`.** Rejected by validation in 0.2.
**Superseded on 2026-11-06**, once a real vocabulary existed — see §3.0.
Tags are a human's grouping judgement, and 91 of 153 live initiatives still
hold legacy-string tag values (roadmap item 15), so a producer reading a
snapshot would learn the wrong shape from the majority of its examples. See §3.

### The data as it stands

Measured read-only against `database.db` on 2026-11-04, because several of the
decisions above turn on it:

| | live rows | notes |
| --- | --- | --- |
| `initiatives` | 153 | 151 have a `responsible_person`; 91 hold legacy-string `tag_groups` |
| `activities` | 48 | 26 have a `start_date`, 5 a `location`; 47 link to an initiative, 48 to a person |
| `people` | 34 | |
| `organisations` | 12 | |
| `contracts` | 6 | |
| `tag_groups` | **0** | the vocabulary the 91 legacy strings refer to is empty |
| `provenance` | **0** | the mechanism has never run against real data |

Three things follow. Activities are the sparse table and the reason to build
this at all. Dates and locations are mostly absent even in hand-entered records,
so an import that cannot supply them is not making the data worse. And an import
would be the **first real exercise of #97** — worth knowing before trusting the
amber-and-unconfirmed path with a batch of 47.

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
  proposes links against superseded rows. The snapshot should be core's output,
  not an invitation to redo the query — `db.get_relation_links` already does it
  for link tables, and `db.get_current_records` was added for record tables,
  which had no such reader (see item C).
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

### 2.4 Who may download it: decided

`snapshot.yaml` is a bulk export of personal data — `people.name`, who worked
on what, when — and the first instinct is that this is a question about *access*,
answered by gating it like the `.db` download. That instinct is wrong here, for
a reason worth stating so it is not re-litigated:

- Access to the whole application is already restricted to
  `@idems.international` addresses (`auth.py:136`). Every signed-in user is a
  colleague, not a third party.
- The Explore spreadsheet already builds a grid column from **every** column of
  every node table, filtering and text-selection enabled
  (`tab_spreadsheet.py:150`). `people` is a node table, so `email` and `role`
  are on screen for any signed-in user today. The same fact is why
  `provenance.md` rejected a JSON provenance column.

So a role gate on the bundle would protect data the same user can read in the
app a click away. It would buy nothing and cost the feature its point, which is
that a contributor hands *their own* quarter's work to an agent without
asking an admin.

The genuinely new thing is not who sees it but **what leaves** — a file on a
laptop, in a model's context, out of reach of the deployment. The right lever is
therefore minimisation, not gating:

- `contract.json` — any signed-in user. It holds no records.
- `snapshot.yaml` — any signed-in user, **`people.email` omitted**. A producer
  needs to *resolve* a person, which a name and an id do; it never needs to
  contact one. Nothing in the format or the validator wants an address.
- `database.db` — unchanged, still `ADMIN_EMAILS`, still the backup tool.

The residual risk is honest and should be written on the page rather than
designed away: a bundle is a point-in-time copy of colleagues' work records that
the deployment can no longer see or revoke. Minimising it is what we can do;
pretending the download is private is not.

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

### 3.0 Tags: refused, then permitted once a vocabulary existed

**Superseded on 2026-11-06.** The reasoning below stands as written and is kept
because one half of it is still load-bearing; what changed is the fact it
rested on. A real vocabulary now exists — three categories and 28 terms, in a
`tag_groups` row pasted into the running deployment rather than committed as
config — so a producer may propose Impact Area and IDEMS Domain terms, and the
format carries them. What that looks like is in
[`suggestions-format.md`](../src/pantograph/producer_docs/suggestions-format.md) §8 and the
[style guide](../src/pantograph/producer_docs/record-style-guide.md).

Which half survived matters. The contract still **cannot list the terms**: they
are rows, so a document generated from config can only say where they live.
What stopped being true is that nothing could *check* a proposed term — the
snapshot carries those rows, and the importer reads them at import time, so it
validates against the vocabulary that exists rather than one frozen at export.
The contract therefore declares instead of refusing, which is exactly what it
already did for a `select_multiple` over a table. The config/data boundary did
not move.

The "better reason" below — that tagging is a judgement a model should not be
making — also survived, but narrowed rather than disappeared. It now applies
per category rather than to the field: **Sociotechnical Innovation** carries
`"producer": false` in the vocabulary row and is dropped from any proposal,
because it is the strategic reading of what a piece of work is *for*. Impact
Area and IDEMS Domain are answerable from the work itself. That the refusal
lives in the row rather than in core is the point: the category is only named
there, and the reason shown to a producer is the one that row gives.

The original reasoning follows.

---

Decided. Validation rejects `tag_groups` in 0.2 rather than accepting and
flagging it, for two independent reasons that happen to agree.

The data reason: 91 of the 153 live initiatives hold old-style keyword strings
in `tag_groups` rather than the object shape `subforms.md` documents — this is
roadmap item 15, and it is why `failsafe_div` renders a MALFORMED SUBFORM DATA
banner on the edit form of every tagged record. A producer handed a snapshot
would therefore learn the wrong shape from the *majority* of its examples, and
the most likely outcome of allowing the field is more banner-rendering rows.
Worse, the `tag_groups` table those 91 values are supposed to name is **empty**,
so there is no vocabulary to choose from even if the shape were right.

The refusal is **derived, not named.** Core names no table, so the implemented
rule is that an element whose groups come from a table rather than from the
config does not accept suggestions — spelled the same way `component_factory`
decides whether a subform is dynamic, which is the presence of
`source_table` / `value_column` / `label_column` in its `parameters`. For this
deployment that is exactly `tag_groups`, in all five forms, and it holds for a
deployment the exporter has never seen. The contract states the refusal and the
reason, so a producer reads it there rather than discovering it in a validation
failure. Email-typed elements are refused by the same mechanism, on the ground
that a contact address is not something to infer from evidence.

The better reason: tags are a grouping judgement about how this organisation
thinks about its work, which is exactly the kind of claim a model should not be
making from commit messages. The field costs nothing to leave empty — 62
initiatives and 32 activities already have no tags — and a human assigning them
during review is not a worse outcome than a human correcting them.

If item 15 lands and tags are wanted later, this is a format version bump and a
validator rule, not a redesign.

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
7. **Similar** names against existing records are surfaced as a non-blocking
   advisory naming the candidate and inviting an `update` or a link instead.
   Decided, and the shape matters — see below.
8. `tag_groups` is rejected outright (§3.0), naming the element.
9. Coverage gaps the producer declared are shown, not buried. The manual run's
   notes evidence stopped five weeks before the period ended and nothing in the
   file said so.

Rule 7 was written as an exact-name check and that would have been useless:
there are **no duplicated names at all** in the live data — not among 153
initiatives, 48 activities, 34 people, 12 organisations or 6 contracts. TODO
item E's three identically-named activities were not live data. So the failure
this rule exists to catch is not a repeated name but *a differently-worded
record for work already recorded* — "anastom framework development" against the
existing "anastom" — which only a similarity measure sees.

Non-blocking, for the reason TODO E has stayed open: duplicate names are
plausibly legitimate, "Weekly standup" and "Site visit" among them, and an
import that refuses them trains people to route around it. The advisory is also
deliberately *not* a general duplicate policy. It is scoped to the one path that
creates the risk at volume — a batch of 47 proposals drafted by something that
cannot see the register's conventions — and leaves item E's question about the
dashboard, the editor and the forms exactly where it is.

The first line of defence is upstream anyway: the producer holds the snapshot
and its instructions require preferring an `update` or a link over a `create`.
Rule 7 is the backstop for when it does so badly.

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

#### Subform granularity: decided at element level, since built per leaf

`provenance.md`'s "Limits" says *a subform's **fields** cannot carry a
provenance*, and that is easy to read — it was read that way in the first draft
of this document — as the activity `description` being unable to carry one at
all. It is narrower than that, and the difference decides how much core work an
import needs.

The subform **element** can already carry one, today, with no change:

- `form_gen.py:80-83` applies `wrap_provenance` to whatever
  `component_for_element` returns, generically, before the relevance wrapper.
  The subform branch is not special-cased out of it.
- The subform element already mounts a parent-namespace store,
  `{"type": "input", "form": form_name, "element": element_id}`, holding the
  whole `{"1": {description, attachments}}` dict — which is the value the
  submit callback collects and `by_element` keys.

A **leaf** — the summary scored separately from the attachments — could not,
when this was written. Leaves render under `activities_form-description`, a
different form namespace, which the submit callback's
`{"type": "provenance", "form": form_name, "element": ALL}` pattern does not
match.

**That is no longer true; item G is built.** A leaf now has a path,
`description.1.description`, and its provenance block mounts under the parent
form keyed by that path while its input keeps the subform's namespace, so both
callbacks reach it unchanged. The reasoning for deferring it was sound on the
evidence available here — what changed is that two more wants arrived pointing
at the same seam, not that this one got stronger.

One claim in the deferral turned out to be the argument against it. The note
below said `_comparable` returns `None` for a dict, so a subform's provenance
is **kept** across an edit, and called that the conservative direction. It is
conservative, but it also means an element-level claim on a subform survives
*any* edit to it — including a complete rewrite of the prose it claims a model
drafted. Per leaf, prose compares exactly again, and a rewritten summary
disowns its origin as every other text field already did.

The other detail still holds and is still why none of this was urgent:
`description` is **not required** on activities, so an unconfirmed summary
never blocks a save. The required set is `name`, one `initiatives_links` and
one `people_links`, all of which carried provenance normally throughout.

#### Producer review is not register confirmation

A value the human settled in chat with the agent carries `reviewed: {by, at}`
in the file. It must not be translated into `confirmed_by`. A signature means
someone read that value *here*; the moment an upload can assert one, the
register stops being defensible, and the mechanism's whole point is that it
cannot be crossed by accident. Default no, and it needs a decision of its own
to become anything else.

That `provenance` holds **0 rows** today sharpens this. There is no body of
confirmed values to compare against, so the first import is also the first
evidence about whether per-field confirmation is workable at volume. Better to
find that out with signatures that mean what they say.

---

## 4.4 What the first real source says about all this

A parallel reading of IDEMS's own eight annual reports — `docs/proposals/idems-report-import.md`
on branch `claude/fervent-boyd-ddffa1` — is the first evidence about this design
from a source nobody built it around. Four of its findings change something
here.

**A source's "activities" are usually initiatives.** The three structured
reports (2018–2020) end in an itemised `Activities` appendix, which sounds like
exactly the input this import wants. It is not: of its 76 entries, 62 are
initiative-shaped, and the 2020 conversion turned 27 appendix entries into 23
initiatives and only 4 activities — the other 39 activities had to be mined out
of the surrounding prose, which was never written to be parsed. So the part of a
document that looks structured feeds the table that is already full, and the
sparse table is fed by the part that is not. The instructions in the bundle
should say so, because a producer reading a well-formed list will reach for it
first.

**Initiative proposals are a join key, not records.** The reading expects 80–90%
of the initiatives it would propose to already exist under a shorter name —
`R-Instat`, not `Development of R-Instat`. That is the similarity advisory (item
J) arriving with its real requirement: the drift is *prefix and gerund*, not
edit distance, and `Investigating IDEMS Kenya` / `Establishing INNODEMS, Kenya` /
`Supporting INNODEMS, Kenya` are three names for one thing. An advisory tuned
for typos would pass all of them. It also wants an alias list, which is a
producer-side artefact and another reason the snapshot is in the bundle.

**Provenance should be `cited`, not `suggested`.** This is the one place the
build is already slightly wrong. A document-derived record is a *citation of a
secondary source* — IDEMS describing its own work a year later, reliable about
what happened and unreliable about when — not a model's inference. `provenance`
already has `cited` as a source and `origin` to hold what was cited, so this
needs no new machinery; what it needs is for the format and the instructions to
carry the distinction rather than defaulting everything to `suggested`. Fold
into item D.

**The funder is the one field the schema cannot record.** Every appendix entry
carries one, and the five appendix sections turn out to be a taxonomy of funding
relationship rather than of work — which is also what predicts an entry's class
in 72 of 76 cases. So the source's primary organising principle has nowhere to
go. `contracts` and `organisations` are adjacent but not it. Worth a decision of
its own before an import discards it silently.

One correction to the brief that produced that reading: it was told the live data
holds about 92 initiatives and 16 activities, which was the roadmap's figure, not
the measured one — it is 153 and 48. The direction of its overlap argument is
unaffected and strengthened. It could not check the overlap for real because it
had no access to the contents, which is precisely the gap `snapshot.yaml` now
closes: the same reading done after item C can match names instead of estimating.

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

### A. ~~Decide the handoff page's data-protection posture~~ — settled

**Labels:** discussion, security, data-protection

Settled in §2.4 on 2026-11-04: any signed-in user, `people.email` omitted from
the snapshot, `.db` download unchanged. No issue needed; recorded here so the
question is not reopened without the two facts that decided it — the
`@idems.international` gate and the spreadsheet already showing every column of
`people`.

Note that `docs/data-protection-model.md` is **not** the home for this. Despite
the name it is the entity model for the ROPA register deployment, not a
statement of Collaboratorium's own posture, and no such document exists. If one
is ever wanted, §2.4 is its first entry.

**Carried into C:** the handoff page states on its face that a bundle is a
point-in-time copy the deployment can no longer see or revoke.

### B. `pantograph export-contract` — **built**

**Labels:** feature, core, integration

Roadmap item 11, built generally rather than for the register. Lives in
`src/pantograph/contract.py`, with the CLI in `__main__.py`, which grew its
first subcommand for it — a bare `python -m pantograph` still serves, because
the container's `ENTRYPOINT` depends on that.

What it emits per element: type, label, `required:` and `relevant:` (verbatim
when they are expressions), choices, link table, and `accepts_suggestions` with
a reason when the format refuses it. Choice lists sourced from
`parameters.source_table` are declared as such and left for the snapshot to
resolve — only `status` keeps its options in the config, and a contract that
inlined the rest would be invalidated by every new person record.

Tested in `tests/test_contract.py`, mostly against a fixture config whose
tables this repository does not have, so a pass cannot be explained by
Collaboratorium's own names.

### C. The handoff page and bundle — **built**

**Labels:** feature, integration
**Depends on:** A, B

`/handoff`, a `login_required` Flask route beside `/admin/maintenance`, serving
one zip — `contract.json`, `snapshot.yaml`, `instructions.md`,
`rejections.yaml` — and one copyable launch line. Assembly is in
`handoff.py` (pure, so a test can read a bundle without a request), the route in
`handoff_routes.py`, the snapshot in `snapshot.py`.

Two things found while building it, worth recording:

**`db.get_all_records` is not the read this wanted**, and neither is
`get_latest_record`, which §2.2 above named. The first returns *every version*
of every non-deleted row — a plain `status != 'deleted'` filter over an
append-only table — and the second returns a single record. So core did not in
fact own the latest-version read, it owned it only for link tables
(`get_relation_links`). `db.get_current_records` is the missing half, and
`get_all_records` is left alone: it has no callers, and the comment on the new
function says what it is there instead of.

**The snapshot states what it withholds.** `omitted_elements` lists
`people.email`, derived by walking the config for email-typed elements rather
than naming the field. Without that a producer comparing the snapshot against
the contract reads a withheld value as an empty one — and an empty address is
exactly the sort of gap something helpful tries to fill.

`rejections.yaml` ships empty, since staging does not exist yet (item E). It
ships anyway so that a producer cannot tell "nothing was rejected" from "no
such file", and so the shape is fixed before anything depends on it.

Tested in `tests/test_handoff.py`, including that a record edited twice appears
once at its latest version, that a link whose newest row is a tombstone is
absent, and that the page states the residual risk — a bundle is a copy that
leaves and cannot be withdrawn — which §2.4 made a requirement rather than a
nicety.

### D. Publish the `collaboratorium-suggestions/0.2` schema

**Labels:** docs, integration

Adopt `anastom`'s §3.7 format, document it in this repository as the consuming
end, and ship a machine-readable schema for it in the bundle. Includes the
`source_ref` anchoring rule, since the manual run's run-date-based refs break
idempotency and sticky rejection on the second run. `tag_groups` is excluded by
the schema itself rather than by a validator rule, so the exclusion travels with
the format (§3.0).

**Acceptance:** a written spec and schema; the manual run's corrected file
validates against it once its `tag_groups` values are dropped; two runs over
unchanged inputs produce identical `source_ref`s; a file setting `tag_groups`
fails schema validation naming the element.

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

**Built as a page plugin** (`pantograph_import`, id `import`), mounted from the
deployment's `plugins:` list like Dashboard and Explore, so it has a nav button
and opens a suggestion in the editor already on screen. A deployment that does
not want it leaves it out of the list. The standalone `/import` and
`/import/queue` routes remain, for a bookmark or a script that posts to them.

### G. Per-leaf provenance inside a subform — **built**

**Labels:** enhancement, forms, core

Deferred here for want of a motivating case, then built once three separate
wants turned out to point at the same seam: per-leaf provenance, a `required:`
reaching one field inside a subform, and per-leaf producer permission — the
last two both raised by the tag-groups work. Any one of them alone was easy to
defer; three is a different argument.

The seam is an address, not a namespace change. A leaf has a path —
`description.1.description` — and its provenance block mounts under the
**parent** form's name keyed by that path, while its input keeps the subform's
own namespace. The submit callback's `element: ALL` and the confirm callback's
`MATCH` then reach it with no change, and the provenance table needed none
either, its `element` column being text. `pantograph.subforms` holds the
vocabulary; `tests/test_subform_leaves.py` covers all three consumers.

It also closed a claim that was quietly too generous. A subform's value is a
dict, which `_comparable` declines to compare, so an element-level provenance
on one survived any edit at all. Per leaf, prose compares exactly: rewriting
the summary drops its provenance, editing the attachments beside it does not.

Still out of reach, and refused at startup rather than evaluated wrongly: a
*conditional* `required:` on a leaf, since an expression inside a subform
resolves against the enclosing form's state — the limit `relevant:` has.

**Acceptance met:** a subform leaf renders, stores and confirms provenance like
any other element, and an edit to one leaf does not disown another's origin.

### J. Similarity advisory on import

**Labels:** feature, data-quality
**Depends on:** E

Decided in §4.1 rule 7. A non-blocking advisory comparing each `create` against
the snapshot and naming a likely match, scoped to the import path only. An
exact-name check is explicitly not it: the live data has zero duplicated names,
so exact matching would find nothing and the real failure is re-wording.

Deliberately not a general duplicate policy — TODO item E stays open for the
dashboard, the editor and the forms.

**Acceptance:** a proposed `create` whose name closely matches a live record is
reported with that record's id and name and an invitation to link or update
instead; it is still staged; the threshold is configurable and the advisory
never refuses an import.

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

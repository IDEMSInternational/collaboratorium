# Roadmap: from the Pantograph split to a data-protection register

Where we are after #54, and what stands between here and a working Records of
Processing Activities deployment with LLM-assisted prefill.

Design rationale lives in [architecture-plugins.md](architecture-plugins.md),
and the register's entity model in
[data-protection-model.md](data-protection-model.md);
this document is the work breakdown. Every item below is filed as an issue
(#56–#72); this page is the map, the issues are where the work is tracked.

## Done

The engine is `pantograph`, Explore and the Dashboard are plugins discovered
through entry points, the package is importable, the editor is decoupled from
the graph, and configuration is a merged directory. An Explore-only deployment
boots clean, so the plugin boundary is real rather than asserted.

## The shape of what remains

The critical path is short and almost entirely **core form capabilities**. A
Record of Processing Activity is a guided checklist: choosing "Legitimate
Interest" as the lawful basis makes Collection Purpose, Necessity and Balance
mandatory; choosing "Consent" makes a different set mandatory. None of that is
expressible today — the core has no conditional logic at all.

    D1, D2  decisions ─────────────┐
                                   ▼
    1 relevance ──► 2 dynamic required ──► 3 constraints ──► 4 multi-page
         │                                                        │
         └────────────────────────────────────────────────────────┤
                                                                  ▼
                                            8 ROPA schema ──► 9 ROPA plugin
                                                                  │
    11 contract export ──► 12 suggestions ingest ──► 13 provenance UI
                                                                  │
                                                       14 analysis pipeline
                                                          (separate repo)

Items 5–7 are independent hygiene and can run in parallel with anything.
Items 15–16 are pre-existing data and UX debt, unrelated to the critical path.

Rough sequencing: decisions and 1–4 first (they ship value to Collaboratorium on
their own — item 2 resolves TODO B); then 8–10 to stand the register up; then
11–14 to bring the LLM work in. 5–7 whenever convenient.

---

# Decisions needed before code

## D1. Do processing activities link to Explore's entities?  ([#56](https://github.com/IDEMSInternational/collaboratorium/issues/56))

**Labels:** discussion, architecture

The framing is "a large number of data fields across a large number of
deployments, each shared with different organisations under different
partnership agreements". Those partnership agreements look a lot like the
existing `contracts` table, and the organisations like `organisations`.

If a processing activity should link to a contract, then the GDPR plugin and
Explore share a schema namespace rather than merely a page slot, and the merged
config directory has to express that: `gdpr.yaml` contributing `tables:` and
`links:` that reference `schema.yaml`'s tables. The merge already supports this
(two files may contribute to one top-level mapping), so it is a modelling
decision, not a technical blocker.

The counter-argument is contamination: we have said the register and the tracker
would be separate sites, partly to keep the early LLM work away from live
collaboration data. Linking the schemas makes a single combined deployment more
attractive and a clean separation harder.

Settle before item 8, because it determines whether the ROPA schema is
standalone or an extension.

**Acceptance:** a written decision recorded in `architecture-plugins.md`, and
`config/gdpr.yaml`'s table list follows from it.

---

## D2. Deployment topology for the second site  ([#57](https://github.com/IDEMSInternational/collaboratorium/issues/57))

**Labels:** discussion, ops

One image with different config, or two images? The plugin system was built as a
build-time seam, so one image plus a different `config/` and a different
`plugins:` list is the intended answer — but it needs confirming, along with
where the register's database lives and whether it shares auth (`ADMIN_EMAILS`,
the `@idems.international` domain check in `auth.py`).

**Acceptance:** a second compose profile or deployment doc that stands up the
register site from the same image, with its own config directory and database.

---

# Core form capabilities

## 1. Relevance: render a field based on the answers above it  ([#58](https://github.com/IDEMSInternational/collaboratorium/issues/58))

**Labels:** enhancement, forms, core

The single biggest core change, and everything in the GDPR plugin depends on it.
Add ODK-style `relevant:` to an element:

```yaml
collection_purpose:
  type: string
  label: Collection Purpose
  relevant: "${lawful_basis} = 'legitimate_interest'"
```

Needs three parts: a small expression evaluator, a per-form callback that
toggles each element's container, and config validation that rejects a
`relevant:` referencing an element that does not exist.

The evaluator must **not** be Python `eval`. Config is operator-supplied and so
nominally trusted, but a form dialect that reaches `eval` is a landmine for
whoever later lets a less-trusted user edit config — and the expression grammar
we need is tiny: `${element}` references, `=`, `!=`, membership for
select_multiple, and `and`/`or`/`not` with parentheses.

Note the interaction with subforms: `component_factory` already renders nested
and dynamic subform blocks, and a `relevant:` inside one has to resolve against
the enclosing form's state. Decide whether that is in scope now or explicitly
deferred.

**Acceptance:** a form defined purely in config where choosing one option
reveals or hides other fields, with no Python change required to add another
conditional field; an invalid `relevant:` expression fails at startup naming the
form and element; hidden fields are not submitted as empty values that overwrite
existing data.

---

## 2. Required follows relevance, and the submit button says what is missing  ([#59](https://github.com/IDEMSInternational/collaboratorium/issues/59))

**Labels:** enhancement, forms, core, ux
**Depends on:** 1

`required` is currently read once when callbacks are registered and frozen into
`validate_required_fields`, so it cannot depend on form state. It has to become
dynamic: a field is required only when it is relevant. Without this, item 1 is
half-useful — the ROPA rule is not "Purpose is required", it is "Purpose is
required *if* you claimed Legitimate Interest".

This also resolves **TODO B**: once the required set is computed per render
rather than baked in, the disabled submit button can name the outstanding fields
instead of saying "Fill Required Fields to Submit" and leaving the user to hunt.

**Acceptance:** a field that is required only under a condition blocks submit
exactly when that condition holds; with a required field empty, the UI states
which field is outstanding; the button enables the moment the last one is
filled.

---

## 3. Constraints and validation messages  ([#60](https://github.com/IDEMSInternational/collaboratorium/issues/60))

**Labels:** enhancement, forms, core
**Depends on:** 1 (shares the expression evaluator)

Validation beyond emptiness, with a per-element message. Retention periods that
must be positive, end dates that must follow start dates, "if you claim an
exemption you must cite it". Reuses item 1's evaluator, so it is much cheaper
built after it than before.

**Acceptance:** an element with a `constraint:` and `constraint_message:` blocks
submit and shows its message when violated; the message is config-supplied, not
generic.

---

## 4. Multi-page forms  ([#61](https://github.com/IDEMSInternational/collaboratorium/issues/61))

**Labels:** enhancement, forms, core

A ROPA record is far too long for one scrolling page. Add a `pages:` grouping
over `elements`, with next/back and per-page validation. Generic, and Explore's
existing forms benefit — the activity form is already long enough that TODO A
exists purely to reorder it.

**Acceptance:** a form declared in pages renders one page at a time with working
navigation; validation runs per page; a partially completed multi-page form
saves and reloads correctly.

---

# Core hygiene

These are independent of the critical path.

## 5. Make the app constructible more than once per process  ([#62](https://github.com/IDEMSInternational/collaboratorium/issues/62))

**Labels:** refactor, testing, core

`create_app()` cannot be called twice: `register_admin_routes` re-registers
routes on the module-global Flask server in `auth.py`, and Flask rejects the
duplicate endpoint. Consequences today are all in testing — it is why the
architectural guard in `test_editor_requests.py` scans core's AST for the string
`"cyto"` instead of the more direct test: build an app with only the dashboard
plugin and assert no callback references an Explore component.

Make the Flask server a factory alongside the Dash app.

**Acceptance:** two apps with different plugin lists can be built in one test
process; the `cyto` guard is rewritten as a plugin-subset assertion.

---

## 6. Move graph element building out of core  ([#63](https://github.com/IDEMSInternational/collaboratorium/issues/63))

**Labels:** refactor, core, plugins

`db.build_elements_from_db` lives in core but reads `node_tables`, which is
Explore's config key, and is only ever called by Explore's data pipeline. It is
harmless today and becomes dead code holding an unsatisfied config dependency
the moment a deployment drops Explore — which the GDPR site may well do.

**Acceptance:** core reads no Explore config key; an Explore-less config passes
validation without defining `node_tables`.

---

## 7. Constrain dependency ranges  ([#64](https://github.com/IDEMSInternational/collaboratorium/issues/64))

**Labels:** ops, dependencies

`requirements.txt` has lower bounds only. `dash>=2.9.0` spans a major version,
and the app's behaviour genuinely varies across it — during the #54 security
review both 2.9.0 and 4.1.0 had to be installed and tested to establish that
`dcc.Markdown(dangerously_allow_html=True)` sanitises in both. CI now exists to
make a pin meaningful, and `requires-python = ">=3.12"` is already declared.

**Acceptance:** upper bounds or a lockfile such that CI and production resolve
the same versions.

---

# The GDPR / ROPA plugin

## 8. ROPA schema and forms in config  ([#65](https://github.com/IDEMSInternational/collaboratorium/issues/65))

**Labels:** feature, gdpr, config
**Depends on:** D1, 1–4

Model a Record of Processing Activity as tables, links and forms: controller and
processor, purposes, categories of data subject and personal data, recipients,
third-country transfers, retention periods, security measures, and the lawful
basis with its conditional follow-ups.

Deliberately config-first. If something cannot be expressed in config, that is
the signal to add the capability to core — not to write it in the plugin.

**Acceptance:** a ROPA can be created and edited end to end through the generic
form engine, with the lawful-basis conditionals working, and no Python written
for the plugin yet.

---

## 9. The `pantograph_gdpr_ropa` plugin: checklist and completeness  ([#66](https://github.com/IDEMSInternational/collaboratorium/issues/66))

**Labels:** feature, gdpr, plugins
**Depends on:** 8

What config cannot express: a view over the register showing which records are
complete, which are missing legally mandatory answers, and which have unanswered
conditional branches. This is the plugin's reason to exist — the forms
themselves should be config.

Declares its `requires_tables` so a deployment without the ROPA schema fails at
startup.

**Acceptance:** a page listing processing activities with their completeness,
naming what is outstanding per record; adding a record navigates into the
generic editor as the dashboard does.

---

## 10. Stand up the register deployment  ([#67](https://github.com/IDEMSInternational/collaboratorium/issues/67))

**Labels:** ops, gdpr
**Depends on:** D2, 9

Its own `config/`, its own database, its own compose profile, its `plugins:`
list mounting the ROPA plugin and whichever Explore tabs are wanted.

**Acceptance:** the register runs from the same image as Collaboratorium with a
different config directory; `UPGRADING.md`-style notes exist for it.

---

# The producer interface and the LLM pipeline

## 11. Export the producer contract, derived from config  ([#68](https://github.com/IDEMSInternational/collaboratorium/issues/68))

**Labels:** feature, gdpr, integration

A CLI that emits a JSON Schema projection of the config containing what an
external producer needs: table, element names, types, choice lists,
required/relevant conditions. Carries a hash of the config it came from.

Derived, never hand-written. A hand-maintained API document drifts from the
config within two sprints; a generated one cannot.

**Acceptance:** `pantograph export-contract` writes a schema an external tool can
validate against; changing an element's choice list changes the exported schema
and its hash.

---

## 12. Ingest suggestions  ([#69](https://github.com/IDEMSInternational/collaboratorium/issues/69))

**Labels:** feature, gdpr, integration
**Depends on:** 11

An authenticated import path accepting a suggestions file. Four properties,
which are much cheaper designed in than retrofitted:

1. **Suggestions are never records.** Proposals against
   `(table, element, value)`; a human confirms. Putting this in the wire format
   means the line cannot later be crossed by accident.
2. **Choice lists validated on import.** The dominant failure mode will be a
   model inventing a lawful basis that is not in the enum. The config holds the
   enum, so reject or flag out-of-vocabulary values.
3. **Stable external keys.** A finding — "field `user.email` at
   `apps/api/models.py`" — has an identity independent of our database ids. Each
   suggestion carries a `source_ref` and ingest dedupes on it, so re-running the
   scanner is idempotent. Without this the third run is unusable.
4. **Rejection is sticky.** A suggestion a human declined must not return on the
   next run. Either export current state alongside the contract, or persist
   rejections by `source_ref`. Decide before the format is fixed.

Start with an authenticated file drop rather than an HTTP endpoint: the artefact
is the audit trail, which matters when the subject is compliance, and
`admin_routes.py` already has an authenticated upload with validation.

**Acceptance:** importing a suggestions file twice produces the same state;
out-of-vocabulary values are rejected naming the element and the allowed values;
a contract-hash mismatch warns rather than silently applying.

---

## 13. Suggested-vs-confirmed field state and provenance  ([#70](https://github.com/IDEMSInternational/collaboratorium/issues/70))

**Labels:** feature, gdpr, forms, core
**Depends on:** 12

`generate_form_layout` already takes `initial_values` — the dashboard uses it to
hand off a pre-linked activity — so the seam exists. What is missing is that a
suggested value must render visibly distinct from a human-entered one and
require explicit confirmation before it counts as answered, with its provenance
stored alongside the value and surfaced in the record and the report.

For a compliance record this is not a UX nicety. A ROPA that cannot distinguish
"a model inferred this purpose" from "the data controller asserted this purpose"
is not a defensible record.

**Acceptance:** a suggested value is visually distinct, does not satisfy a
required field until confirmed, and its source and confidence are visible on the
record and in the exported report.

---

## 14. The static-analysis pipeline (separate repository)  ([#71](https://github.com/IDEMSInternational/collaboratorium/issues/71))

**Labels:** feature, gdpr, integration
**Depends on:** 11

Not a plugin and not an importer of core. A batch producer that reads a codebase,
identifies stored data fields, drafts purposes, and emits a suggestions file
conforming to the exported contract.

Separate because it keeps model SDKs, API keys and source-code read access out
of a web application whose entire subject is data protection; because it runs on
its own cadence in CI or on a laptop; and because an organisation must be able
to run the register with no LLM exposure at all.

**Acceptance:** running it against a repository produces a suggestions file that
item 12 imports without manual editing.

---

# Pre-existing debt

## 15. Migrate legacy `tag_groups` values  ([#72](https://github.com/IDEMSInternational/collaboratorium/issues/72))

**Labels:** bug, data-quality

Every non-empty `tag_groups` value in the database is an old-style keyword string
such as `"education technology research"` rather than the object shape
`docs/subforms.md` documents, so `failsafe_div` renders a "MALFORMED SUBFORM
DATA" banner on the edit form of every tagged record: 92 initiatives, 16
activities, 9 organisations, 2 contracts.

The failsafe is working as designed; the data needs migrating. Append-only
versioned schema, so this creates new version rows rather than updating. Dry-run
and report unmappable values first; back up the database.

**Acceptance:** no record renders the failsafe banner; unmappable values are
reported rather than silently dropped; the migration is re-runnable.

---

## 16. TODO A, C, D, E

**Labels:** see TODO.md

[TODO.md](../TODO.md) items A (activity form field order), C (editor modal is a
dead end after save), D (Bootstrap Icons never load) and E (duplicate record
policy) are unchanged and unrelated to this roadmap. Item B is absorbed by
item 2 above.

Item C is worth pulling forward: the register will make "add a record" the
common path just as the dashboard did, so a rough edge on save gets seen
constantly rather than rarely.

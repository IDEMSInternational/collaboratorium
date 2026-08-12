# The data-protection register: entity model and decisions

Design record for the Records of Processing Activities deployment. The work
breakdown is in [roadmap.md](roadmap.md); this is the modelling reasoning behind
it.

## Decisions taken

**A fully separate system on the common framework.** Separate server, separate
schema, separate database. Some schema elements will resemble Collaboratorium's
— organisations and agreements look much like `organisations` and `contracts` —
but they are defined for this deployment, not shared with it. This closes #56.

The earlier framing of that question ("does the GDPR plugin link to Explore's
entities?") was wrong and worth correcting, because it smuggled in a false
premise. Explore owns no tables; it renders whatever `node_tables` lists. Tables
belong to the deployment's `config/schema.yaml`. A plugin may *depend on* tables
and declare that with `requires_tables`, but nothing owns them.

**Maximum deduplication of justifications**, with a comparison gate — see
"Assessment reuse" below.

**Version-pinned citations.** Editing a shared justification must not silently
change what past records claim.

## Entity model

Four framings were considered. They describe the same graph; the choice is
which questions are one hop away and which are a report.

| centred on | makes cheap | weak at |
| --- | --- | --- |
| Processing activity | the Art. 30 report | "everything we share with X" |
| Flow / disclosure | "who gets what, under which agreement" | Art. 30 grouping |
| Data field | "what do we hold, where" | purpose, which varies per use |
| Agreement | "what does this DPA permit" | internal processing with no agreement |

The activity-centred model follows Art. 30's wording, but the problem this
register exists to solve — many data fields across many deployments, each shared
with different organisations under different agreements — describes **flows**.

A flow record is really the activity↔organisation link promoted to a node, which
is what makes the four-way relationship (organisation, in a role, under an
agreement, for an activity) expressible at all: a two-column link table cannot
hold it. Its edges read as question words — *what, from, whose, to, under, why* —
which makes the form design fall out of the model.

These are not competing hubs so much as **groupings of one fact along different
dimensions**: a star schema, with the processing record as the fact and product,
deployment, agreement, organisation, purpose and data field as dimensions.
Grouping by any dimension yields a different register view, which is what
`filter_registry` and `views:` already do for Explore.

So the decision is not "which hub" but **what is one row?**

### The grain: decided

**`(scope, field, purpose, recipient, data subject category)`.**

Each dimension earned its place by a question that could not otherwise be
answered in one hop:

| dimension | the question that forced it |
| --- | --- |
| purpose | the same field is collected for two purposes under different lawful bases |
| scope | two deployments of the same product treat the same field differently; and a subject access request may be scoped to one deployment or partner |
| recipient | the same field and purpose can go to two recipients under different bases or safeguards — a domestic partner and a third-country one |
| data subject category | the same field is collected from different categories of data subject under different terms |

Recipient and data subject category are modelled as **links**, not as text or a
multi-select blob. Promoting a dimension into the grain later is mechanical if it
was already a relationship, and a re-interpretation of every existing row if it
was not.

Cardinality is not the constraint it appears to be. Logical rows for a product
with ~200 fields across ~12 deployments run to five figures, but stored rows are
the scope defaults plus their exceptions — see below.

## Scope is a hierarchy, not two levels

The same product is deployed many times — ParentApp Kenya, ParentApp India — and
deployments share roughly 90% with the base, diverging in local variables and
customised behaviour. But a deployment is not the finest level either: within one
deployment, separate **programs** can be entered through different joining
triggers and collect different data. A state running hybrid delivery with
in-person follow-ups collects things the fully-online national program does not.

That is a third level of the same relationship, so scope is modelled as a **tree**
rather than two fixed levels:

    Product → Deployment → Program → …

A processing record attaches at any level and is inherited by everything below
it, overridden only where reality diverges. Two hardcoded levels would have been
known-insufficient on arrival, and a fourth level — region, cohort — is
plausible.

Note that program membership is *not* a data subject category. The people are
still parents; what differs is the program they entered through. Encoding
delivery mode into the category vocabulary produces "parents (hybrid)" and
"parents (online)", and the moment a second axis appears the categories multiply
combinatorially. Data subject category remains its own dimension — staff,
beneficiaries, facilitators genuinely differ — but it is not the home for this.

**Data fields are defined once at the product level, not per deployment.** The
static analysis scans a codebase once and its inventory applies to every scope
beneath it. Modelling fields per deployment multiplies the work by the number of
deployments for no gain.

What a scope stores per field is a **status**, not a value:

- **added** — a local variable the parent scope does not have
- **removed** — a field this scope does not collect, because the feature is off
- **overridden** — same field, different purpose, recipient or retention

Removal matters as much as addition. A register claiming a deployment processes
biometrics when that feature is switched off is wrong in the direction that
costs credibility.

The tree also gives the fingerprint comparison (#81) a natural traversal: compare
a program against its deployment, and a deployment against its product, rather
than against every assessed field everywhere.

## Justifications are entities, not text fields

The legitimate-interest test has three written parts — purpose, necessity,
balancing — and they are frequently identical across deployments. Retyping them
produces near-duplicates that diverge over time, which is materially worse than
one shared text: a regulator can line them up and ask why they differ.

The three parts are independently reusable, **and** an Assessment binds one of
each into the combination that was actually reviewed, carrying its reviewer and
date. Processing records cite the Assessment, not the parts. This deduplicates
at both levels without ever producing an assessment that no one signed off as a
test.

Consequences:

- The form is not three textareas. It is "cite an existing assessment, or write
  a new one" — a `select_one` over assessments plus a create path. A register
  that merely *could* deduplicate will not.
- Links carry `(id, version)`, not `id`. "Approved against Assessment v3, and v4
  now exists" is a state the register must be able to show.
- The same reuse applies to the other Art. 30 prose — security measures,
  retention justification, transfer safeguards. One mechanism, not four.

## Assessment reuse

When a deployment is assessed, each field is fingerprinted and compared against
fields already assessed:

- **identical** → inherit the assessment, no review
- **changed** → a human reviews the diff, and either reassesses or accepts the
  divergence and records why
- **not seen before** → assess from scratch

"Accept, record why" is a first-class outcome, not a failure. It needs its own
record — what diverged, who decided, why the extra risk is acceptable. That is
the reasoning a regulator asks for and the thing that otherwise never gets
written down.

**The fingerprint is the calibration.** Too inclusive and every incidental
wording change blocks reuse, which defeats the purpose. Too sparse and a
deployment silently inherits an assessment that does not apply, which is worse
than having none. Column name, type and question text are the core; whether
purpose and recipient belong in the fingerprint or are compared separately is
open.

Question text matters because two deployments can share a column name while
asking a differently-worded question, and so collect subtly different data. The
unit of reuse is the field **in its collection context**, not the column.

**The gate fires on upgrade too.** A release that edits a question's wording in
an existing deployment is the same event: the fingerprint moved and the
assessment may no longer hold. Treating "new deployment" and "new version of an
existing one" identically gives drift detection for free.

### The register derives the fingerprint; the scanner does not

The scanner emits **raw attributes** — column name, type, question text, source
location — and the register computes the fingerprint from them. The division
matters for two reasons.

**A definition change should not mean re-scanning every codebase.** The
composition above will be wrong at least once. If the scanner computes the
fingerprint, correcting it is a campaign across every repository; if the register
derives it from stored attributes, it is a re-derivation over data already held.
The scanner also stays dumber and more stable, which matters most for the
component that will be iterated on constantly early on.

**The pipeline then needs no read access to the compliance database.** It emits
facts one way, which is the better posture for a component holding model API
keys and source-code access, and it removes the round-tripping problem entirely.

The reviewer-facing output is still a diff — "six fields changed since the last
release, three materially" is what keeps the register true, and a fresh list of
everything is not. But that diff is computed here, from what the scan reports
against what the register already holds.

### A fingerprint definition change is a mass re-review event

Widen the definition and every field's fingerprint moves at once, so every
inherited assessment lands in the "changed" branch — thousands of records
demanding review because someone added a field to a tuple.

So the definition is **versioned**, and the version that produced each stored
fingerprint is recorded, letting the register distinguish *"these diverged
because the definition changed"* from *"these diverged because the data did"*.
Without that, the first definition change reads as a compliance emergency.
Keeping the definition small and stable is the other half of the answer.

## One mechanism, three appearances

The same shape has now arrived from three directions:

- inherited from the product vs set on this deployment
- a shared assessment vs a justification specific to this record
- model-suggested vs human-confirmed (#70)

Each is *a value, where it came from, and whether someone here stood behind it*.
That is one capability and it belongs in core, not the GDPR plugin — building it
once means the LLM prefill work inherits the deployment-inheritance UI, and vice
versa.

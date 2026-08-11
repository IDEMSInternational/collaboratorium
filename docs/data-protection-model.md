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

### The open question: grain

The grain must be the finest question the register will ever be asked. If
"does deployment X share date-of-birth with organisation Y?" must be answerable,
the grain is `(deployment, field, recipient)`. Coarser and it cannot be
answered; finer and rows are created that nobody fills in.

Worth testing against the questions actually received: a subject access request,
a partner asking what is held on their behalf, and a regulator asking for
Art. 30 all probe at different grains. The finest wins.

## Product and deployment are different things

The same product is deployed many times — ParentApp Kenya, ParentApp Malaysia —
and deployments share roughly 90% with the base, diverging in local variables
and customised behaviour.

**Data fields are therefore defined once per product, not once per deployment.**
The static analysis scans a codebase once and the inventory applies to every
deployment of it. Modelling fields per deployment multiplies the work by the
number of deployments for no gain.

A processing record attaches to the product by default and is inherited by every
deployment, with per-deployment records only where reality diverges. Divergence
comes in three kinds, and what is stored per deployment is a **status**, not a
value:

- **added** — a local variable the base does not have
- **removed** — a base field this deployment does not collect
- **overridden** — same field, different purpose, recipient or retention

Removal matters as much as addition. A register claiming a deployment processes
biometrics when that feature is switched off is wrong in the direction that
costs credibility.

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

This reframes the analysis pipeline (#71). Its highest-value output is not an
inventory but a **diff** — "six fields changed fingerprint since the last
release, three materially". Inventory is a one-off; diff keeps the register
true.

## One mechanism, three appearances

The same shape has now arrived from three directions:

- inherited from the product vs set on this deployment
- a shared assessment vs a justification specific to this record
- model-suggested vs human-confirmed (#70)

Each is *a value, where it came from, and whether someone here stood behind it*.
That is one capability and it belongs in core, not the GDPR plugin — building it
once means the LLM prefill work inherits the deployment-inheritance UI, and vice
versa.

# Provenance and confirmation

A value in a form may carry a record of where it came from, and of whether
anyone here has stood behind it. An unconfirmed value renders visibly distinct
and does not satisfy a `required:` element.

The same shape arrived from three independent directions:

- a field **inherited** from the product versus **set** on this deployment
- a **shared** assessment **cited** versus a justification written for this record
- a value the model **suggested** versus one a human **confirmed**

Each is *a value, where it came from, and whether someone here stood behind it*.
That is one capability, so it lives in core rather than in the GDPR plugin —
building it once means the LLM prefill work inherits the deployment-inheritance
UI, and vice versa.

For a compliance record this is not a UX nicety. A register that cannot
distinguish "a model inferred this purpose" from "the controller asserted this
purpose" is not a defensible record.

## The shape

```python
{
  "source": "entered" | "inherited" | "cited" | "suggested",
  "from": None,          # a scope id, an [assessment_id, version] pair, an analysis run id
  "confidence": 0.82,    # only meaningful for "suggested"
  "confirmed_by": None,
  "confirmed_at": None,
}
```

`from` means whatever its source needs it to mean. Core carries it, shows it and
stores it; only the thing that produced the value knows how to read it.

A value counts as **confirmed** when `source` is `entered`, or when
`confirmed_by` is set. Everything else is unconfirmed.

## Absent provenance means "entered"

This is the invariant the rest is built around. Every record and form written
before any of this existed keeps working unchanged, and a deployment that never
supplies a provenance sees no difference at all: nothing is wrapped, no store is
rendered, and `required:` behaves exactly as it did.

So `is_confirmed(None)` is true, and an explicit `{"source": "entered"}` is
normalised away to nothing.

The one thing that is *not* treated as absent is a provenance that is present
but unreadable — an unknown source, a value that is not a record at all. That is
kept and treated as unconfirmed. Silently promoting data we cannot parse into "a
human typed this" is the failure this whole mechanism exists to prevent.

## Confirming

Confirming is not retyping. The value still says it was suggested or inherited,
which is the fact a regulator asks about; only the signature is added. There is
no "unconfirm" — a signature that can be quietly withdrawn is not a signature,
and editing the value is the way to disown it.

Confirmation is **per field**, not per record. A single "confirm everything"
button would be the fastest way to make the mechanism meaningless, since the
signature is meant to mean that someone read *that* value.

## What the form does

An element rendered with a provenance is wrapped in a block carrying an origin
line, a confirm control, and a `dcc.Store` holding the record. Only elements
that actually carry one are wrapped, so an existing form renders exactly the DOM
it rendered before.

Unconfirmed is amber and dashed, deliberately unlike the red left-border a
required field carries: "nobody has stood behind this yet" is a different claim
from "this is missing", and a user who cannot tell them apart cannot act on
either. The submit button says so too:

    Add Name and confirm Collection Purpose to submit

"Add Collection Purpose" would be baffling for a field the user can see is
already filled in.

As with `required:`, the disabled button is a courtesy and not a gate. The same
check runs on submit, and a save carrying an unconfirmed answer to a required
question is refused with `Not saved — not confirmed: …`.

## Supplying a provenance

`generate_form_layout` takes a `provenances` map alongside `initial_values`:

```python
generate_form_layout(
    "ropa_form", forms_config,
    initial_values={"collection_purpose": "to keep participants informed"},
    provenances={"collection_purpose": provenance.record(
        "suggested", origin="run-4", confidence=0.82)},
)
```

It is a parallel map rather than a wrapper around each value because several
element types are already dict- or list-valued, and a value that might or might
not be a `{"value": …}` box would have to be unpicked in every one of them.

An editor request or a `form-prefill` store carries it under a `provenance` key,
so a page that wants to open a prefilled form — a scope inheriting from its
parent, an ingested suggestions file — needs no change in core.

## Where it is stored

A table of its own, one row per value that somebody did not simply type:

```
provenance(record_table, record_id, record_version, element,
           source, origin, confidence, confirmed_by, confirmed_at)
```

Core creates it, on every start rather than only for a fresh database —
provenance arrived after the deployments did, and the ones with records to
defend are exactly the ones that already have a database.

The record tables have a column per element and no home for a record *about* a
value. Three shapes were considered:

| shape | why not |
| --- | --- |
| `<element>_provenance` per element | multiplies the schema, and a migration every time an element is added |
| one JSON column per record | invisible to SQL, and visible to everything that does `SELECT *` |
| a table beside the record | the join, and the usual risk of drifting from the row |

The JSON column is the tempting one — it rides along on the row for free, and
the row is the version. What rules it out is not the awkward SQL but the
`SELECT *`: the graph builds node properties from every column, and the
spreadsheet builds a grid column from every column, so a deployment that has
never supplied a provenance would start seeing a column of raw JSON. Being
invisible to a deployment that does not use it is the promise the whole
mechanism is built on.

The drift objection to a side table does not survive keying on the **version**.
The schema is append-only, so a saved row never changes; provenance written
against `(id, version)` in the same transaction as that row cannot come to
describe a value that has moved on. It needs no id or version discipline of its
own, because it borrows the record's. And the columns are columns rather than a
blob, so the question the mechanism exists to answer stays a query:

```sql
SELECT record_table, record_id, element FROM provenance WHERE confirmed_by IS NULL
```

`origin` is the `from` key, stored JSON-encoded: core does not interpret it, and
a scope id, an `[assessment_id, version]` pair and an analysis run id are not
the same type. Only one encoding round-trips all three.

An **absent row means "entered"**, exactly as an absent record does in memory.
Nothing is written for a value a human typed, so the table stays empty for a
deployment that never supplies a provenance, and every record written before any
of this existed reads back exactly as it did.

## Editing a value disowns its origin

A value a human has since rewritten was entered, whatever record travelled with
it on the page. Confirming is not retyping, and retyping is not confirming — so
on save, a provenance whose value has changed since the version being replaced
is dropped rather than stored. Before persistence this did not much matter,
because a stale claim died with the page; now it would be written into the
register as a standing assertion that a model wrote prose a person typed.

Doubt keeps the provenance rather than clearing it. Dropping it asserts "a
human typed this", which is the claim nothing here may make by accident, so only
values that compare exactly — text against text, a number against the number in
the column — are ever judged to have changed. A checkbox's `True` against the
`1` in its column, or a subform's dict against the JSON string it was stored as,
differ in their spelling alone, and those keep what they had.

## What the export shows

Where a value came from is appended to the value, not gathered into a footnote:

    ## Newsletter signup

    to keep participants informed _[Suggested by run-4 (82% confidence), not confirmed]_

A reader who has to look elsewhere to learn that nobody stood behind a purpose
will read that purpose as asserted, and the export is the artefact a regulator
is handed. The annotation is matched on the record's version as well as its id,
so a report rendered from an older version never borrows a newer one's claims.

## Limits

**A subform's fields cannot carry one.** A subform renders its inputs under its
own form namespace, the same limit `relevant:` has.

**A links element's provenance survives an edit to it.** Link values are stored
in a link table and read back as an unordered list, which does not compare
exactly, so editing one leaves the origin note in place rather than risking a
false claim of authorship. It stays unconfirmed, and the edit form still shows
it.

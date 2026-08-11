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

## Limits

**Provenance is not yet persisted.** It survives from prefill through rendering,
confirmation and the submit gate, but the record tables have a column per
element and nowhere to put it, so what is saved is the value alone. An
unconfirmed value on an *optional* field is therefore stored as though it had
been entered. Giving provenance a home in the schema is the next piece of work,
and until it lands the export cannot show provenance either.

**A subform's fields cannot carry one.** A subform renders its inputs under its
own form namespace, the same limit `relevant:` has.

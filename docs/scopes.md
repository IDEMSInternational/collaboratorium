# Scope resolution

The same product is deployed many times — ParentApp Kenya, ParentApp India — and
a deployment is not the finest level either: within one deployment, separate
programs are entered through different joining triggers and collect different
data. So scope is a **tree**:

    Product → Deployment → Program → …

A processing record attaches at any level and applies to everything beneath it.
`scopes.py` answers the one question that follows from that: given the tree and
the records attached around it, what does the register actually say about *this*
scope?

It is a pure library — no database, no Dash, no config. The modelling reasoning
behind it is in [data-protection-model.md](data-protection-model.md).

## The grain, and what resolution moves along

A record is `(scope, field, purpose, recipient, data subject category)`.
Resolution runs along **scope** only; the other four form the key that decides
whether a record beneath overrides one above. `recipient` and
`data_subject_category` are link ids, and this module never looks inside them.

```python
tree = ScopeTree([
    {"id": "parentapp"},
    {"id": "india", "parent": "parentapp"},
    {"id": "state_hybrid", "parent": "india"},
])

resolve(tree, records, "state_hybrid")   # effective records for one scope
resolve_all(tree, records)               # {scope_id: records}, one traversal
divergences(tree, records, "india")      # {grain_key: added | removed | overridden}
```

**Depth is never counted.** Nothing in the library names a level or branches on
how deep one is, so a fourth level — region, cohort — is a row in the scope
table and no code change. Two hardcoded levels would have been
known-insufficient on arrival.

**Several roots are allowed.** An organisation runs more than one product, and a
synthetic "everything" node above them would invite a record attached to it,
which would then be inherited by products that share nothing.

## Only divergences are stored

A product with ~200 fields across a dozen deployments implies five-figure
logical rows. Stored rows are the scope defaults plus their exceptions, which is
hundreds. Inheritance is what makes the grain affordable.

Of the three divergence kinds, only one is stored:

| kind | stored? | why |
| --- | --- | --- |
| **removed** | yes, as a tombstone | an absence cannot mean this — absence is what inheritance is for |
| **added** | as an ordinary record | derivable: no ancestor declares this key |
| **overridden** | as an ordinary record | derivable: an ancestor does |

`added` and `overridden` are the same stored thing and differ only in what sits
above. Asking an author to classify their own edit invites a register whose
labels disagree with its rows, so `divergences` derives the label from the tree.
It also moves on its own, correctly: an addition becomes an override the moment
the level above acquires the same key.

**Removal matters as much as addition.** A register claiming a deployment
processes biometrics when the feature is switched off is wrong in the direction
that costs credibility. A tombstone is never itself an effective record — a
removal says nothing is processed — so `resolve` drops it and `divergences`
reports it. The register shows removals in its divergence view, not its rows.

A scope may re-declare a key an ancestor removed, and it reads as `added`:
the parent, having removed it, does not have it.

## Provenance

A record that reached a scope by inheritance is returned marked, following the
contract shared with #70/#82:

```python
{"source": "inherited", "from": "parentapp",
 "confidence": None, "confirmed_by": None, "confirmed_at": None}
```

`from` is the scope that **declared** it, not the immediate parent — that is the
scope you would edit to change what this one shows. Absent provenance means
"entered", so a record resolved at the scope that declared it is returned
exactly as given; the resolver invents nothing and mutates nothing.

Confidence and confirmation carry across untouched. They are facts about how the
record came to be written, and a child scope inheriting it does not re-witness
them.

## What is rejected rather than guessed

A cycle, a parent that is not a scope, a duplicate scope id, a record on an
unknown scope, a record with no field, and two records at one scope sharing a
grain key. That last one has no defined precedence, and picking one silently
would make the register depend on row order.

**A missing dimension is a key value, not a wildcard.** A record with no
recipient states something about the field with no recipient; it is not a
default that a recipient-bearing record silently overrides. Wildcards would make
override order depend on specificity as well as depth, and two orderings that
can disagree is one too many.

Row order is stable across runs and independent of input order. A register that
reshuffles its rows between two identical runs is unreviewable.

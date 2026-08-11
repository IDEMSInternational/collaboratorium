# Conditional fields: `relevant:`

Show a form element only when a condition over the answers above it holds. The
motivating case is a records-of-processing checklist, where the lawful basis you
pick decides which further questions you are legally required to answer:

```yaml
lawful_basis:
  type: select_one
  label: Lawful Basis
  list_name: basis_list
  basis_list:
    consent: Consent
    legitimate_interest: Legitimate Interest

collection_purpose:
  type: string
  label: Collection Purpose
  relevant: "${lawful_basis} = 'legitimate_interest'"
```

Adding another conditional field is a config edit. No Python is involved.

## The expression language

Deliberately small, and deliberately not Python `eval` — config is
operator-supplied and so nominally trusted, but a form dialect that reaches
`eval` is a landmine for whoever later lets a less-trusted user edit config.

| | |
| --- | --- |
| element reference | `${element_name}` |
| linked-row reference | `${link_element.column}` |
| comparison | `=` `!=` `>` `>=` `<` `<=` |
| multi-select membership | `selected(${tags}, 'health')` |
| logic | `and` `or` `not`, with parentheses |
| literals | `'text'`, `"text"`, `42`, `3.14`, `true`, `false`, `null` |

`=` is equality, following ODK, whose conventions this config dialect already
borrows. `==` is a syntax error.

```yaml
relevant: "${lawful_basis} = 'consent'"
relevant: "${retention_years} > 5"
relevant: "selected(${data_categories}, 'health') or selected(${data_categories}, 'biometric')"
relevant: "not ${is_internal} and ${country} != 'GB'"
relevant: "${responsible_person}"          # answered at all
```

### Semantics worth knowing

**Emptiness is falsehood.** An unanswered question is not a yes: `""`, `[]`,
`null` and `0` are all false. A bare `${x}` therefore reads as "x has been
answered". This matches the emptiness test the submit button already uses, so
"answered" means the same thing to `relevant:` as it does to `required:`.

**Numbers compare numerically even when held as strings.** A `dcc.Input` yields
a string even for a field the config declares as an integer, so `${n} > 5` is
true for `"10"`. If either side is not numeric, both are compared as strings.

**A multi-select uses `selected()`.** As a convenience a single-choice
multi-select compares equal to that choice, but anything longer will not equal a
scalar. Values are also accepted comma-joined, because that is how they come
back from the database — an expression behaves the same on an edit form as on an
add form.

**An unknown element reads as empty, not as an error.** A partially filled form
would otherwise be unusable. References are checked at startup instead.

## Reading across a link

`${data_field.special_category}` reads a column of the row a link element points
at, so a form can stop asking a question the linked row has already answered:

```yaml
data_field:
  type: select_one
  label: Data Field
  parameters:
    source_table: data_fields
    value_column: id
    label_column: name

article_9_condition:
  type: select_one
  label: Article 9 Condition
  list_name: article_9_condition_list
  relevant: "${data_field.special_category} = 'yes'"
  required: "${data_field.special_category} = 'yes'"
```

This is a correctness feature, not a convenience. Without it a processing record
re-asks whether the data is special category when `data_fields` already records
it, and whether the recipient is outside the UK/EEA when `organisations` already
implies it — so the register holds the same fact twice, with nothing to stop the
copies disagreeing.

The part before the dot is an element of *this* form, and it must be a link:
something with `parameters.source_table`. A `select_one` over an inline list is a
vocabulary rather than a reference to a row, and `${status.name}` is rejected.

### Semantics worth knowing

**A reference through an unset link reads as empty.** A question about a row
nobody has picked is not a yes, so it behaves exactly like an unanswered element
and the condition is false.

**The current version of the linked row is what is read**, and a row whose
current version is `deleted` reads as empty rather than as the values it last
held. This is `get_latest_record`, the same answer the rest of the app gives.

**A reference crosses at most one link.** `${data_field.product.name}` is a
parse error. Two hops would let one form's condition walk the whole schema, and
each hop is a row fetch on every keystroke.

**The condition re-fires when the link changes**, because the link element is
what the callback watches — the linked row can only change identity when the
link is re-pointed. An *edit to the linked row itself*, made in another tab
while this form is open, is not noticed until the form is reloaded. The check
that decides is the one that runs on submit, and that one re-reads the row.

**The link's `value_column` must be `id`.** The row is fetched by id; a link
keyed on anything else is refused at startup rather than resolved against the
wrong row.

**The lookup is not something an expression can invent.** The evaluator has no
database of its own: it calls a resolver built from this form's own
`parameters:` and can read nothing the config did not already point at.

## Validation

Every expression is parsed when the app starts, and each name it references is
checked against the elements of the same form. A mistake stops the deployment
rather than surfacing later as a field that silently never appears:

```
pantograph.relevance.FormConfigError: contracts_form.organisation_person:
  'relevant' references 'organisaton', which is not an element of that form.

pantograph.relevance.FormConfigError: contracts_form.organisation_person:
  Unexpected '=' at position 17 in '${organisation} === '
```

A cross-link reference is checked against the *linked table's* columns, so a
misspelt column is caught at startup too rather than becoming a condition that
is quietly always false:

```
pantograph.relevance.FormConfigError: processing_records_form.article_9_condition:
  'relevant' reads ${data_field.special_categry}, but 'special_categry' is not a
  column of 'data_fields'.

pantograph.relevance.FormConfigError: processing_records_form.article_9_condition:
  'relevant' reads ${status.name}, but 'status' is not a link — only an element
  with parameters.source_table points at a row.
```

Writing `lawful_basis` where you meant `${lawful_basis}` is the likeliest
authoring slip, so that error names the fix.

## What gets stored

**An answer to a question that no longer applies is stored as NULL.** A record
claiming a legitimate-interest balancing test when the basis has since been
changed to Consent would be worse than one that simply does not answer, so a
stale answer is not kept.

Nothing is lost. The schema is append-only and versioned, so the previous answer
remains in the record's history — a new version is written with the field
cleared, and the old version still holds it.

Relevance is recomputed on the server at submit rather than inferred from what
was on screen. Visibility is a client-side fact and the client is not the
authority on what gets written.

## `required:` follows relevance

`required:` takes the same expression language, so a field can be required only
under a condition:

```yaml
collection_purpose:
  type: string
  relevant: "${lawful_basis} = 'legitimate_interest'"
  required: "${lawful_basis} = 'legitimate_interest'"
```

`required: true` on a conditional element means "required whenever you can see
it", which is the common case and needs no expression.

**A field is never required while it is not relevant.** Relevance always wins,
so a form cannot demand an answer to a question it is not showing — which would
be unfillable, with no cue as to why.

Because the outstanding set is recomputed per render rather than frozen when
callbacks are registered, the disabled submit button names the fields it is
waiting for:

    Add Name and Linked Initiatives to submit

Four or more outstanding fields are summarised — `Add Name, Notes and 2 more to
submit` — since reciting a long list is worse than a count.

A conditionally required field still shows the required asterisk. The label is
rendered once and cannot know the answers, and being required in some states is
closer to the truth than no cue at all.

The disabled button is a courtesy to the user, not a gate: the client posts the
callback directly and can send whatever it likes. The same check runs on submit,
and a save that arrives with questions unanswered is refused with
`Not saved — still needed: …`.

## Limits

`relevant:` on a **subform** element is rejected at startup rather than silently
ignored. A subform renders its inputs under its own form namespace, so the
enclosing form's callback cannot see their state. Supporting it means giving
subform state a path back to the parent, which is its own piece of work.

A **`select_one` still cannot filter its source table** — offering only
product-level scopes, or only justifications of a matching `kind`. It wants the
same expression language pointed the other way, at the candidate rows rather
than at one linked row, and it wants the options rebuilt by a callback rather
than at layout time. That is its own piece of work.

Only elements that carry a `relevant:` are wrapped in a container, so a form
with no conditions renders exactly as it did before, and a form with conditions
registers exactly one extra callback watching only the elements its conditions
actually read.

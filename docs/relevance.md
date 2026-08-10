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

Only elements that carry a `relevant:` are wrapped in a container, so a form
with no conditions renders exactly as it did before, and a form with conditions
registers exactly one extra callback watching only the elements its conditions
actually read.

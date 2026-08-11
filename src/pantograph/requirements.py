"""
requirements.py
Which questions must be answered right now, and saying so.

`required:` used to be a static boolean read once when callbacks were
registered and frozen into the validation, so it could not depend on the state
of the form. Two things follow from making it dynamic:

**A field can be required only under a condition.** The rule a
records-of-processing checklist actually needs is not "Purpose is required", it
is "Purpose is required *if* you claimed Legitimate Interest". `required:` now
takes the same expression language as `relevant:`:

    collection_purpose:
      type: string
      relevant: "${lawful_basis} = 'legitimate_interest'"
      required: "${lawful_basis} = 'legitimate_interest'"

That includes a condition reading across a link — `${data_field.special_category}`
— because the two keywords take one language and a field whose relevance comes
from the linked row almost always takes its obligation from there too.

**A field is never required while it is not relevant.** Otherwise a form could
demand an answer to a question it is not showing — unfillable, with no cue as to
why. Relevance always wins, so `required: true` on a conditional element means
"required whenever you can see it", which is the common case and needs no
expression at all.

Because the outstanding set is now recomputed per render rather than baked in,
the disabled submit button can finally name the fields it is waiting for instead
of saying "Fill Required Fields to Submit" and leaving the user to hunt — the
long-standing TODO B, which mattered because on the activity form the required
fields are 1st, 11th and 13th.

**An unconfirmed value does not answer the question.** A value a model suggested
or a parent scope supplied is on screen, but nobody here has stood behind it, so
`required:` is not satisfied until someone does. It is a second reason a field
can be outstanding, and the button distinguishes them — telling a user to "Add
Purpose" when Purpose is visibly filled in would be baffling. See
`provenance.py`; a field with no provenance was entered here and is confirmed by
definition, so a form that has never heard of provenance is unaffected.
"""
from dash import ALL, Input, Output, State

from pantograph import provenance as prov
from pantograph.expressions import ExpressionError, evaluate, is_truthy, parse, referenced_elements
from pantograph.relevance import (
    FormConfigError,
    check_link_references,
    compile_form,
    link_resolver,
    value_key,
)

# ODK spells booleans this way in form definitions; anything else is an expression.
_TRUE = (True, "yes", "true")
_FALSE = (False, None, "", "no", "false")

ENABLED_LABEL = "Submit"


def is_static_required(raw):
    """True when `required:` is a plain yes, rather than a condition."""
    return raw in _TRUE


def can_be_required(raw):
    """
    True when the element is required in at least some state.

    Used for the label's asterisk, which is rendered once and cannot know the
    answers: a conditionally required field is marked, because being required in
    some states is closer to the truth than no cue at all.
    """
    return raw not in _FALSE


def compile_required(form_name, form_config, schema=None):
    """
    {element_id: True | ast} for every element that can be required.

    `True` means unconditionally; an AST means it depends on the answers.
    """
    compiled = {}
    for element_id, element in (form_config.get("elements") or {}).items():
        raw = element.get("required")
        if raw in _FALSE:
            continue
        if is_static_required(raw):
            compiled[element_id] = True
            continue
        if not isinstance(raw, str):
            raise FormConfigError(
                f"{form_name}.{element_id}: 'required' must be yes/no or an "
                f"expression, not {raw!r}"
            )
        try:
            compiled[element_id] = parse(raw)
        except ExpressionError as exc:
            raise FormConfigError(f"{form_name}.{element_id}: 'required': {exc}") from exc

    known = set(form_config.get("elements") or {}) | set(form_config.get("meta") or {})
    for element_id, node in compiled.items():
        if node is True:
            continue
        unknown = sorted(referenced_elements(node) - known)
        if unknown:
            raise FormConfigError(
                f"{form_name}.{element_id}: 'required' references "
                f"{', '.join(repr(u) for u in unknown)}, which "
                f"{'is not an element' if len(unknown) == 1 else 'are not elements'} "
                f"of that form."
            )
        check_link_references(form_name, element_id, "required", form_config, node, schema)
    return compiled


def validate_forms(config):
    """Startup check, alongside the one relevance does for `relevant:`."""
    return {
        form_name: compile_required(form_name, form_config, config.get("tables"))
        for form_name, form_config in (config.get("forms") or {}).items()
    }


def unsatisfied(form_config, values, form_name="<form>", provenances=None, resolve=None):
    """
    (unanswered, unconfirmed): the two ways a required question can fail to be
    settled, kept apart because the cure for each is different.

    Relevance is applied first: a question the form is not showing is never
    outstanding.
    """
    required = compile_required(form_name, form_config)
    if not required:
        return [], []

    # One resolver for the whole pass, so a rule that appears in both an
    # element's `relevant:` and its `required:` — which is the common shape —
    # fetches the linked row once.
    if resolve is None:
        resolve = link_resolver(form_config)

    relevant = compile_form(form_name, form_config)
    unanswered, unconfirmed = [], []
    for element_id, condition in required.items():
        relevance_condition = relevant.get(element_id)
        if relevance_condition is not None and not evaluate(relevance_condition, values, resolve):
            continue
        if condition is not True and not evaluate(condition, values, resolve):
            continue
        if not is_truthy(values.get(element_id)):
            unanswered.append(element_id)
        elif not prov.is_confirmed((provenances or {}).get(element_id)):
            unconfirmed.append(element_id)
    return unanswered, unconfirmed


def outstanding(form_config, values, form_name="<form>", provenances=None, resolve=None):
    """Element ids that do not settle their `required:`, whichever way they fail."""
    unanswered, unconfirmed = unsatisfied(form_config, values, form_name, provenances, resolve)
    return unanswered + unconfirmed


def rejection_message(form_config, values, form_name="<form>", provenances=None, resolve=None):
    """
    The refusal to show when a submit arrives with questions unanswered, or None
    if it may proceed.

    The disabled submit button is a courtesy to the user, not a gate: the client
    posts the callback directly and can send whatever it likes. This is the
    check that actually decides, and it is a function so it can be tested — the
    submit callback itself is a closure built per form at registration time.
    """
    unanswered, unconfirmed = unsatisfied(form_config, values, form_name, provenances, resolve)
    clauses = []
    if unanswered:
        clauses.append("still needed: " + _names(form_config, unanswered))
    if unconfirmed:
        clauses.append("not confirmed: " + _names(form_config, unconfirmed))
    if not clauses:
        return None
    return "Not saved — " + "; ".join(clauses)


def _names(form_config, element_ids):
    return ", ".join(label_for(form_config, element_id) for element_id in element_ids)


def label_for(form_config, element_id):
    element = (form_config.get("elements") or {}).get(element_id, {})
    return element.get("label") or element_id.replace("_", " ")


def submit_label(form_config, missing, unconfirmed=()):
    """
    What the submit button should say.

    Naming the fields is the whole point, so the list is only summarised once it
    is long enough that naming them all would be worse than a count. Values that
    are present but unconfirmed get their own verb: "Add Purpose to submit" is
    nonsense for a field the user can see is already filled in.
    """
    clauses = []
    if missing:
        clauses.append(f"Add {_recite(form_config, missing)}")
    if unconfirmed:
        verb = "confirm" if clauses else "Confirm"
        clauses.append(f"{verb} {_recite(form_config, unconfirmed)}")
    if not clauses:
        return ENABLED_LABEL
    return " and ".join(clauses) + " to submit"


def _recite(form_config, element_ids):
    labels = [label_for(form_config, element_id) for element_id in element_ids]
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    if len(labels) == 3:
        return f"{labels[0]}, {labels[1]} and {labels[2]}"
    return f"{labels[0]}, {labels[1]} and {len(labels) - 2} more"


def watched_elements(form_name, form_config):
    """
    Everything the submit button's state depends on: the fields that can be
    required, plus whatever their conditions and relevance conditions read.
    """
    required = compile_required(form_name, form_config)
    if not required:
        return []

    relevant = compile_form(form_name, form_config)
    names = set(required)
    for element_id in required:
        node = required[element_id]
        if node is not True:
            names |= referenced_elements(node)
        if element_id in relevant:
            names |= referenced_elements(relevant[element_id])
    return sorted(names)


def register_required_callbacks(app, forms_config):
    """One callback per form that has anything required."""
    for form_name, form_config in (forms_config or {}).items():
        watched = watched_elements(form_name, form_config)
        if not watched:
            continue

        elements = form_config.get("elements") or {}
        inputs = [
            Input({"type": "input", "form": form_name, "element": name},
                  value_key(elements.get(name, {})))
            for name in watched
        ]

        # Provenance stores only exist for elements that were rendered carrying
        # one, so on a form that has none this pattern matches nothing and the
        # callback sees a pair of empty lists — exactly the state it had before.
        inputs.append(Input(prov.store_id(form_name, ALL), "data"))
        inputs.append(State(prov.store_id(form_name, ALL), "id"))

        @app.callback(
            Output({"type": "submit", "form": form_name}, "disabled"),
            Output({"type": "submit", "form": form_name}, "children"),
            *inputs,
            prevent_initial_call=False,
        )
        def validate_required_fields(*current, _fc=form_config, _watched=watched, _name=form_name):
            answers = dict(zip(_watched, current[:-2]))
            provenances = prov.by_element(current[-1], current[-2])
            unanswered, unconfirmed = unsatisfied(_fc, answers, _name, provenances)
            return (bool(unanswered or unconfirmed),
                    submit_label(_fc, unanswered, unconfirmed))

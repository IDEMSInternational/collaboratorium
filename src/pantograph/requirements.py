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
"""
from dash import Input, Output

from pantograph.expressions import ExpressionError, evaluate, is_truthy, parse, referenced_elements
from pantograph.relevance import FormConfigError, compile_form, value_key

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


def compile_required(form_name, form_config):
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
    return compiled


def validate_forms(config):
    """Startup check, alongside the one relevance does for `relevant:`."""
    return {
        form_name: compile_required(form_name, form_config)
        for form_name, form_config in (config.get("forms") or {}).items()
    }


def outstanding(form_config, values, form_name="<form>"):
    """
    Element ids that must be answered and are not, given the current answers.

    Relevance is applied first: a question the form is not showing is never
    outstanding.
    """
    required = compile_required(form_name, form_config)
    if not required:
        return []

    relevant = compile_form(form_name, form_config)
    missing = []
    for element_id, condition in required.items():
        relevance_condition = relevant.get(element_id)
        if relevance_condition is not None and not evaluate(relevance_condition, values):
            continue
        if condition is not True and not evaluate(condition, values):
            continue
        if not is_truthy(values.get(element_id)):
            missing.append(element_id)
    return missing


def rejection_message(form_config, values, form_name="<form>"):
    """
    The refusal to show when a submit arrives with questions unanswered, or None
    if it may proceed.

    The disabled submit button is a courtesy to the user, not a gate: the client
    posts the callback directly and can send whatever it likes. This is the
    check that actually decides, and it is a function so it can be tested — the
    submit callback itself is a closure built per form at registration time.
    """
    missing = outstanding(form_config, values, form_name)
    if not missing:
        return None
    names = ", ".join(label_for(form_config, element_id) for element_id in missing)
    return f"Not saved — still needed: {names}"


def label_for(form_config, element_id):
    element = (form_config.get("elements") or {}).get(element_id, {})
    return element.get("label") or element_id.replace("_", " ")


def submit_label(form_config, missing):
    """
    What the submit button should say.

    Naming the fields is the whole point, so the list is only summarised once it
    is long enough that naming them all would be worse than a count.
    """
    if not missing:
        return ENABLED_LABEL
    labels = [label_for(form_config, element_id) for element_id in missing]
    if len(labels) == 1:
        return f"Add {labels[0]} to submit"
    if len(labels) == 2:
        return f"Add {labels[0]} and {labels[1]} to submit"
    if len(labels) == 3:
        return f"Add {labels[0]}, {labels[1]} and {labels[2]} to submit"
    return f"Add {labels[0]}, {labels[1]} and {len(labels) - 2} more to submit"


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

        @app.callback(
            Output({"type": "submit", "form": form_name}, "disabled"),
            Output({"type": "submit", "form": form_name}, "children"),
            *inputs,
            prevent_initial_call=False,
        )
        def validate_required_fields(*current, _fc=form_config, _watched=watched, _name=form_name):
            missing = outstanding(_fc, dict(zip(_watched, current)), _name)
            return bool(missing), submit_label(_fc, missing)

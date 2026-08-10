"""
relevance.py
`relevant:` on a form element — show it only when its condition holds.

The condition is written in the expression language in `expressions.py`:

    collection_purpose:
      type: string
      label: Collection Purpose
      relevant: "${lawful_basis} = 'legitimate_interest'"

Three moving parts, all here:

1. `validate_forms` parses every expression at startup and checks each name it
   references is an element of the same form. A form dialect that fails at first
   click instead of at boot is a bad trade for the person deploying it.
2. `register_relevance_callbacks` adds one callback per form that toggles the
   container of each conditional element as the answers it depends on change.
3. `irrelevant_elements` recomputes the same conditions server-side at submit,
   because the visibility of a component is a client-side fact and the client is
   not the authority on what gets written.

**Answers to questions that no longer apply are stored as NULL.** A record
claiming a legitimate-interest balancing test when the basis has since been
changed to Consent would be worse than one that simply does not answer. Nothing
is lost: the schema is append-only and versioned, so the previous answer remains
in the record's history.

Not in scope yet: `relevant:` *inside* a subform block. Subforms render their
own inputs under a separate form namespace, so their state is not visible to the
enclosing form's callback. A `relevant:` there is rejected by `validate_forms`
rather than silently ignored.
"""
from dash import Input, Output, html

from pantograph.expressions import ExpressionError, evaluate, parse, referenced_elements

# How to read the current value of each element type off its component. Mirrors
# the mapping in form_gen's submit registration; they must agree or an
# expression would read the wrong property.
VALUE_KEY = {
    "date": "date",
    "datetime": "date",
    "subform": "data",
    "table": "data",
}

VISIBLE = {"display": "block"}
HIDDEN = {"display": "none"}


def value_key(element_config):
    return VALUE_KEY.get(element_config.get("type"), "value")


def container_id(form_name, element_id):
    return {"type": "relevance", "form": form_name, "element": element_id}


def wrap(component, form_name, element_id):
    """
    Put a conditional element in an addressable container.

    Wrapping here rather than inside `component_for_element` keeps every element
    type's rendering untouched — an element with no `relevant:` is not wrapped at
    all, so nothing about an existing deployment's DOM changes.
    """
    return html.Div(component, id=container_id(form_name, element_id))


# --------------------------------------------------------------------------
# Config validation
# --------------------------------------------------------------------------

class FormConfigError(Exception):
    """Raised for a form whose `relevant:` expressions cannot be honoured."""


def _compiled(form_config):
    """{element_id: ast} for every element of this form carrying a `relevant:`."""
    compiled = {}
    for element_id, element in (form_config.get("elements") or {}).items():
        expression = element.get("relevant")
        if expression:
            compiled[element_id] = parse(expression)
    return compiled


def compile_form(form_name, form_config):
    """Parse and check one form's expressions. Raises FormConfigError."""
    elements = form_config.get("elements") or {}
    known = set(elements) | set(form_config.get("meta") or {})

    compiled = {}
    for element_id, element in elements.items():
        expression = element.get("relevant")
        if not expression:
            continue
        if element.get("type") == "subform":
            raise FormConfigError(
                f"{form_name}.{element_id}: 'relevant' on a subform element is not "
                f"supported yet — a subform renders its inputs in its own "
                f"namespace, so the enclosing form cannot see their state."
            )
        try:
            node = parse(expression)
        except ExpressionError as exc:
            raise FormConfigError(f"{form_name}.{element_id}: {exc}") from exc

        unknown = sorted(referenced_elements(node) - known)
        if unknown:
            raise FormConfigError(
                f"{form_name}.{element_id}: 'relevant' references "
                f"{', '.join(repr(u) for u in unknown)}, which "
                f"{'is not an element' if len(unknown) == 1 else 'are not elements'} "
                f"of that form."
            )
        compiled[element_id] = node
    return compiled


def validate_forms(config):
    """
    Check every form in the config. Called at startup so a bad expression stops
    the deployment rather than surfacing as a field that never appears.
    """
    compiled = {}
    for form_name, form_config in (config.get("forms") or {}).items():
        compiled[form_name] = compile_form(form_name, form_config)
    return compiled


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------

def irrelevant_elements(form_config, values):
    """
    Which of this form's elements are not currently applicable.

    `values` maps element name to submitted value. Recomputed server-side at
    submit rather than trusting what the browser had on screen.
    """
    hidden = set()
    for element_id, node in compile_form("<submit>", form_config).items():
        if not evaluate(node, values):
            hidden.add(element_id)
    return hidden


def register_relevance_callbacks(app, forms_config):
    """One callback per form with conditional elements."""
    for form_name, form_config in (forms_config or {}).items():
        compiled = compile_form(form_name, form_config)
        if not compiled:
            continue

        elements = form_config.get("elements") or {}
        # Only the elements actually referenced drive the callback; watching
        # every field would re-run it on every keystroke anywhere in the form.
        watched = sorted({name for node in compiled.values() for name in referenced_elements(node)})
        conditional = sorted(compiled)

        inputs = [
            Input({"type": "input", "form": form_name, "element": name},
                  value_key(elements.get(name, {})))
            for name in watched
        ]
        outputs = [
            Output(container_id(form_name, element_id), "style")
            for element_id in conditional
        ]

        @app.callback(outputs, inputs, prevent_initial_call=False)
        def toggle(*current, _compiled=compiled, _watched=watched, _conditional=conditional):
            return styles_for(_compiled, _watched, _conditional, current)


def styles_for(compiled, watched, conditional, current_values):
    """
    The callback's whole body, as a plain function so it can be tested without
    a live app. `current_values` is positional, matching `watched`.
    """
    context = dict(zip(watched, current_values))
    return [
        VISIBLE if evaluate(compiled[element_id], context) else HIDDEN
        for element_id in conditional
    ]

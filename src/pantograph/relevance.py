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

A condition can also read a column of a linked row —
`relevant: "${data_field.special_category} = 'yes'"` — so a form stops asking a
question the row it points at has already answered. The expression language
knows nothing about the database: this module hands `evaluate` a resolver built
from the form's own `parameters:`, and that resolver is the only thing that
touches storage. It is built fresh per evaluation, so its per-row cache lives
for one callback firing and cannot serve a stale row on the next.

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

from pantograph.expressions import (
    ExpressionError,
    evaluate,
    parse,
    referenced_elements,
    referenced_links,
)

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


def link_target(element_config):
    """
    The table a select element draws its options from, or None if it is not a
    link at all — a `select_one` over an inline list is a vocabulary, not a
    reference to a row.
    """
    parameters = element_config.get("parameters") or {}
    return parameters.get("source_table")


def check_link_references(form_name, element_id, keyword, form_config, node, schema=None):
    """
    Check every `${link.column}` in one expression. Raises FormConfigError.

    Two separate mistakes, and the message has to distinguish them: pointing at
    an element that is not a link, and naming a column the linked table does not
    have. The second can only be caught when the schema is to hand, which it is
    at startup — the point of the check is that a typo stops the deployment
    rather than surfacing as a condition that is quietly always false.
    """
    elements = form_config.get("elements") or {}
    for link_name, column in sorted(referenced_links(node)):
        table = link_target(elements.get(link_name) or {})
        if not table:
            raise FormConfigError(
                f"{form_name}.{element_id}: {keyword!r} reads "
                f"${{{link_name}.{column}}}, but {link_name!r} is not a link — "
                f"only an element with parameters.source_table points at a row."
            )
        parameters = elements[link_name].get("parameters") or {}
        value_column = parameters.get("value_column")
        if value_column != "id":
            # The row is fetched by id. A link keyed on anything else would need
            # a different lookup, and silently reading the wrong row is worse
            # than refusing at boot.
            raise FormConfigError(
                f"{form_name}.{element_id}: {keyword!r} reads "
                f"${{{link_name}.{column}}}, but {link_name!r} selects on "
                f"{value_column!r} rather than 'id'. A linked row is fetched by id."
            )
        if schema is None:
            continue
        fields = (schema.get(table) or {}).get("fields") or {}
        if not fields:
            raise FormConfigError(
                f"{form_name}.{element_id}: {keyword!r} reads "
                f"${{{link_name}.{column}}}, but {link_name!r} points at "
                f"{table!r}, which is not a table in this config."
            )
        if column not in fields:
            raise FormConfigError(
                f"{form_name}.{element_id}: {keyword!r} reads "
                f"${{{link_name}.{column}}}, but {column!r} is not a column of "
                f"{table!r}."
            )


def compile_form(form_name, form_config, schema=None):
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
        check_link_references(form_name, element_id, "relevant", form_config, node, schema)
        compiled[element_id] = node
    return compiled


def validate_forms(config):
    """
    Check every form in the config. Called at startup so a bad expression stops
    the deployment rather than surfacing as a field that never appears.
    """
    compiled = {}
    for form_name, form_config in (config.get("forms") or {}).items():
        compiled[form_name] = compile_form(form_name, form_config, config.get("tables"))
    return compiled


# --------------------------------------------------------------------------
# Reading across a link
# --------------------------------------------------------------------------

def _fetch_linked_row(table, object_id):
    """
    The current row of `table` with this id, or {} if there is none.

    Imported here rather than at module scope so that a deployment with no
    cross-link reference never pulls the database module in to satisfy a
    condition, and so tests of the language need no database at all.
    """
    from pantograph.db import get_latest_record

    return get_latest_record(table, object_id) or {}


def link_resolver(form_config, fetch=None):
    """
    A `resolve(link_element, column, link_value)` for `evaluate`.

    Build one per evaluation, not per form: the cache exists so that six
    conditions reading six columns of one linked row cost one query, and a cache
    outliving the callback that made it would answer with a row the user has
    since edited.

    `get_latest_record` decides what "the linked row" means, and its answers are
    the ones this feature wants: the highest version, and nothing at all for a
    row whose current version is deleted. A reference into a deleted row
    therefore reads as unanswered, like a link nobody has set.
    """
    elements = form_config.get("elements") or {}
    fetch = fetch or _fetch_linked_row
    rows = {}

    def resolve(link_name, column, link_value):
        if link_value is None or (isinstance(link_value, str) and not link_value.strip()):
            return None
        table = link_target(elements.get(link_name) or {})
        if not table:
            return None
        key = (table, str(link_value))
        if key not in rows:
            rows[key] = fetch(table, link_value)
        return rows[key].get(column)

    return resolve


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------

def irrelevant_elements(form_config, values, resolve=None):
    """
    Which of this form's elements are not currently applicable.

    `values` maps element name to submitted value. Recomputed server-side at
    submit rather than trusting what the browser had on screen — including the
    linked rows, which are re-read here rather than taken from the client.
    """
    if resolve is None:
        resolve = link_resolver(form_config)
    hidden = set()
    for element_id, node in compile_form("<submit>", form_config).items():
        if not evaluate(node, values, resolve):
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
        def toggle(*current, _compiled=compiled, _watched=watched,
                   _conditional=conditional, _fc=form_config):
            return styles_for(_compiled, _watched, _conditional, current,
                              link_resolver(_fc))


def styles_for(compiled, watched, conditional, current_values, resolve=None):
    """
    The callback's whole body, as a plain function so it can be tested without
    a live app. `current_values` is positional, matching `watched`.
    """
    context = dict(zip(watched, current_values))
    return [
        VISIBLE if evaluate(compiled[element_id], context, resolve) else HIDDEN
        for element_id in conditional
    ]

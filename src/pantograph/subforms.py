"""
subforms.py
Addressing one field inside a subform.

A subform renders its inputs under a form namespace of its own — `activities_form-description`
— with component ids of the form `{group}|{field}`. That namespace is what made a
subform's fields invisible to everything that works per element: provenance,
`required:`, and the producer contract all match on the *parent* form's
elements, and a leaf is not one.

This module is the seam. A leaf has a **path** relative to the parent form:

    description.1.description        the activity summary
    tag_groups.3.impact_area         one dropdown of a tag group

That path is what the three mechanisms key on, so none of them has to know how a
subform is rendered, and the provenance table needs no change at all — its
`element` column is text, and a path is text.

The path is deliberately *not* the `{group}|{field}` component id. That spelling
belongs to Dash, inside the subform's own namespace, and it does not say which
element of the parent form it is part of. Converting between the two happens
here and nowhere else.

**A dynamic subform's leaves cannot be enumerated from config**, because its
groups come from a table — that is the same fact that makes the contract refuse
to state its values. So `static_leaves` walks only subforms whose groups are
written in the config. Provenance works for both regardless, because a
provenance is *supplied by a caller* rather than compiled from config, and the
renderer walks the record's actual value.
"""
SEPARATOR = "."
COMPONENT_SEPARATOR = "|"

# The keys whose presence makes a subform's groups come from a table rather than
# from the config. Spelled the same way `component_factory` decides it.
_VOCABULARY_KEYS = {"source_table", "value_column", "label_column"}


def is_dynamic(element_config):
    """True when this subform's groups come from a table."""
    return _VOCABULARY_KEYS.issubset((element_config or {}).get("parameters") or {})


def leaf_path(element_id, group, field):
    """The path naming one field of one group of a subform element."""
    return f"{element_id}{SEPARATOR}{group}{SEPARATOR}{field}"


def split_leaf(path):
    """
    `(element_id, group, field)`, or None when `path` is not a leaf path.

    Split from the left on exactly two separators, so a field whose name
    contains a dot stays intact — the element id and the group id are the parts
    this module controls, the field name comes from a deployment's config or
    from a row in its database.
    """
    if not isinstance(path, str):
        return None
    parts = path.split(SEPARATOR, 2)
    if len(parts) != 3 or not all(parts):
        return None
    return tuple(parts)


def is_leaf_path(path):
    return split_leaf(path) is not None


def component_element_id(group, field):
    """The id a leaf's input carries inside the subform's own namespace."""
    return f"{group}{COMPONENT_SEPARATOR}{field}"


def subform_form_name(form_name, element_id):
    """The namespace a subform renders its inputs under."""
    return f"{form_name}-{element_id}"


def _as_mapping(value):
    """A subform's value as a dict, whatever shape it arrived in."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        import json
        try:
            loaded = json.loads(value)
        except (ValueError, TypeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def leaf_value(values, path, default=None):
    """
    The value at `path` in a form's values, or `default`.

    `values` is keyed by element, and a subform's entry may be a dict or the
    JSON string it was stored as — both shapes occur, depending on whether the
    values came from a browser or from a database row.
    """
    split = split_leaf(path)
    if split is None:
        return default
    element_id, group, field = split
    group_values = _as_mapping(_as_mapping(values).get(element_id)).get(group)
    if not isinstance(group_values, dict):
        return default
    return group_values.get(field, default)


def static_leaves(form_config):
    """
    `(path, leaf_config)` for every field of every statically-defined subform in
    a form, which is every leaf the config can name.

    Dynamic subforms are skipped; their groups are rows in another table, so
    there is nothing here to walk. A deployment that wants a rule on one of
    those declares it in that row's `key_values`, which is data rather than
    config and so is somebody else's problem to read.
    """
    for element_id, element in ((form_config or {}).get("elements") or {}).items():
        if (element or {}).get("type") != "subform" or is_dynamic(element):
            continue
        for group, fields in (element.get("parameters") or {}).items():
            if not isinstance(fields, dict):
                continue
            for field, leaf in fields.items():
                if isinstance(leaf, dict) and leaf.get("type"):
                    yield leaf_path(element_id, group, field), leaf


def leaf_label(form_config, path):
    """
    What to call a leaf in a message to a person.

    "Summary" rather than "description.1.description", and qualified with the
    element's own label when it has one that says anything — a bare "Summary"
    is ambiguous the moment two subforms both have one.
    """
    split = split_leaf(path)
    if split is None:
        return path
    element_id, group, field = split
    element = ((form_config or {}).get("elements") or {}).get(element_id) or {}
    group_config = ((element.get("parameters") or {}).get(group) or {})
    leaf = group_config.get(field) if isinstance(group_config, dict) else None
    name = (leaf or {}).get("label") or field.replace("_", " ")
    outer = element.get("label")
    return f"{outer} — {name}" if outer else name


def _is_empty(value):
    return value in (None, "", [])


def prune_empty_groups(value):
    """
    A subform's value without the groups that hold nothing.

    The form keeps an emptied group on screen so it can be filled again; what is
    stored should not carry one. `value` is the JSON text the form holds, or a
    mapping when the form was opened with one. Returns the same kind of thing it
    was given, with every group whose fields are all empty removed. A value that
    is not a group mapping is returned untouched.
    """
    import json

    given_text = isinstance(value, str)
    try:
        groups = json.loads(value) if given_text and value.strip() else value
    except ValueError:
        return value
    if not isinstance(groups, dict):
        return value

    kept = {}
    for key, group in groups.items():
        if isinstance(group, dict):
            if any(not _is_empty(field) for field in group.values()):
                kept[key] = group
        elif not _is_empty(group):
            kept[key] = group
    return json.dumps(kept, indent=2) if given_text else kept


def overlay(existing, proposed):
    """
    A subform's stored value with a proposal laid over it, leaf by leaf.

    A proposal that names only the summary must not take the attachments beside
    it away, and "an update never removes anything" is the rule the suggestions
    format promises. So a leaf the proposal does not mention keeps what is
    stored, a list leaf (attachments) is added to — a row already present, by
    its url, is not added twice — and any other leaf the proposal does set
    replaces the stored one. Returns a mapping, whatever shape either arrived in.
    """
    merged = {group: dict(fields) if isinstance(fields, dict) else fields
              for group, fields in _as_mapping(existing).items()}
    for group, fields in _as_mapping(proposed).items():
        if not isinstance(fields, dict):
            merged[group] = fields
            continue
        have = merged.setdefault(group, {})
        if not isinstance(have, dict):
            have = merged[group] = {}
        for leaf, value in fields.items():
            if _is_empty(value):
                continue
            if isinstance(value, list):
                rows = list(have.get(leaf) or [])
                seen = {_row_key(r) for r in rows if not _row_empty(r)}
                # A stored row with nothing in it is the blank the form keeps for
                # adding another; it is not an attachment to preserve.
                rows = [r for r in rows if not _row_empty(r)]
                rows += [r for r in value if _row_key(r) not in seen]
                have[leaf] = rows
            else:
                have[leaf] = value
    return merged


def _row_empty(row):
    return not isinstance(row, dict) or all(_is_empty(v) for v in row.values())


def _row_key(row):
    """What makes two attachment rows the same one: the link, else the whole row."""
    if isinstance(row, dict):
        return row.get("url") or tuple(sorted((k, str(v)) for k, v in row.items()))
    return row


def as_leaves(element_config, proposed):
    """
    A proposed subform value as `{group: {leaf: value}}`.

    A suggestion staged before the importer read leaves holds the summary as a
    bare string. It means the first text leaf of the first group, which is what
    the form already does with one, so say so here and the overlay can keep the
    other leaves.
    """
    if not isinstance(proposed, str) or not proposed.strip():
        return proposed
    for group, fields in ((element_config or {}).get("parameters") or {}).items():
        for leaf, spec in (fields or {}).items():
            if isinstance(spec, dict) and spec.get("type") == "string":
                return {str(group): {leaf: proposed}}
    return proposed

"""
contract.py
The producer contract: what an external tool needs in order to propose records.

Derived from the merged config, never hand-written. A document restating the
element inventory drifts from `config/` within two sprints; a generated one
cannot, and carrying a hash of the config it came from means a proposal drafted
against last quarter's form can be detected rather than merely surprising.

See docs/agentic-ingest.md §2.1. Core names no table here: every statement in
the exported contract is read off the config, so the same exporter serves a
deployment whose tables it has never heard of.

Two things the contract deliberately does *not* do:

**It does not resolve choice lists.** Only `status` keeps its options in the
config; every other `select_one` / `select_multiple` reads
`parameters.source_table`, so the vocabulary is data. The contract says *where*
the options come from and leaves the values to the snapshot, because a contract
that inlined them would be invalidated by every new person record.

**It does not promise that every element may be proposed.** An element the
format refuses carries `accepts_suggestions: false` and the reason, so a
producer learns it from the contract rather than from a validation failure.
"""
import hashlib
import json
from datetime import datetime, timezone

# Bumped when the shape of the exported document changes in a way a producer
# would notice. The config hash answers a different question — "was this drafted
# against the form as it is now" — and the two are independent.
CONTRACT_FORMAT = "pantograph-contract/1"

# The wire format this contract describes proposals in. Owned by this
# repository because it is the consuming end: see docs/agentic-ingest.md §6.
SUGGESTIONS_FORMAT = "collaboratorium-suggestions/0.3"

# The keys whose presence makes a subform's groups come from a table rather
# than from the config. Spelled the same way component_factory decides it, and
# for the same reason — one rule, read off `parameters`.
_VOCABULARY_KEYS = {"source_table", "value_column", "label_column"}

_NOT_REQUIRED = (False, None, "", "no", "false")
_REQUIRED = (True, "yes", "true")


def config_hash(config):
    """
    A stable digest of the merged config.

    Canonical JSON with sorted keys, so the merge order of the config directory
    cannot change the hash while the content stays the same — the whole point is
    that a producer can tell "the form changed" from "the files were renamed".
    """
    canonical = json.dumps(dict(config), sort_keys=True, separators=(",", ":"),
                           default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _condition(raw):
    """`required:` / `relevant:` as the contract states it."""
    if raw in _NOT_REQUIRED:
        return None
    if raw in _REQUIRED:
        return True
    # An expression, passed through verbatim. The producer does not need to
    # evaluate it — it needs to know that the answer above decides this one.
    return {"when": raw}


def _choices(element):
    """
    Where this element's options come from, or None if it has none.

    Two shapes, because the config has two. `list_name` names a sibling key
    holding the options literally, which is how `status` is written; everything
    else points at a table.
    """
    parameters = element.get("parameters") or {}
    if _VOCABULARY_KEYS.issubset(parameters):
        return {
            "from_table": parameters["source_table"],
            "value_column": parameters["value_column"],
            "label_column": parameters["label_column"],
            "resolved_in": "snapshot",
        }

    list_name = element.get("list_name")
    if list_name and isinstance(element.get(list_name), list):
        options = {"values": list(element[list_name])}
        if "default" in element:
            options["default"] = element["default"]
        return options

    return None


def _subform(element):
    """A subform's groups, and whether they are config or data."""
    parameters = element.get("parameters") or {}
    if _VOCABULARY_KEYS.issubset(parameters):
        return {
            "kind": "dynamic",
            "vocabulary": {
                "from_table": parameters["source_table"],
                "value_column": parameters["value_column"],
                "label_column": parameters["label_column"],
                # The terms are data, so they are not listed here. Read them
                # from the snapshot's rows for this table: each row's
                # `key_values` names its categories, and each category names
                # its terms. A category carrying `"producer": false` is one
                # this deployment will not take a proposed value for, and the
                # import drops it with the reason that row gives.
                "resolved_in": "snapshot",
            },
        }
    groups = {
        group_id: {
            field_id: _leaf_contract(field)
            for field_id, field in (fields or {}).items()
            if isinstance(field, dict)
        }
        for group_id, fields in parameters.items()
    }
    return {"kind": "static", "groups": groups}


def _leaf_contract(field):
    """
    One field of a static subform, as the contract states it.

    A leaf gets the same three statements a top-level element does — what it
    is, whether it must be answered, and whether a producer may propose it —
    because all three are now addressable per leaf. The path is
    `<element>.<group>.<field>`; see pantograph.subforms.
    """
    stated = {"type": field.get("type"), "label": field.get("label")}
    if field.get("required") in _REQUIRED:
        stated["required"] = True
    if field.get("producer") is False:
        stated["accepts_suggestions"] = False
        stated["refused_because"] = (
            field.get("producer_note")
            or "this deployment does not accept a proposed value for it")
    return stated


def _refusal(element):
    """
    Why the suggestions format will not carry a value for this element, or None.

    Both rules are read off the config rather than off a table name, so they
    hold for a deployment this exporter has never seen.
    """
    element_type = element.get("type")

    # A vocabulary subform — a tag grouping — used to be refused here, on the
    # ground that neither the contract nor the importer could state or check a
    # valid value. Half of that was always true and is still: the terms are
    # rows in another table, so this document cannot list them. The other half
    # was only true while the table was empty. The snapshot carries those rows,
    # and the importer reads them at import time, so a proposed term can be
    # checked against the vocabulary that actually exists.
    #
    # So the contract declares where the terms live rather than refusing, which
    # is exactly what it already does for a `select_multiple` over a table.
    # Permission per category lives in the vocabulary row too, because that is
    # the only place a category is named.

    if element_type == "email":
        return "a contact address is not something to infer from evidence"

    return None


def element_contract(element):
    """One element, as the contract states it."""
    stated = {"type": element.get("type")}

    if element.get("label"):
        stated["label"] = element["label"]

    required = _condition(element.get("required"))
    if required is not None:
        stated["required"] = required

    relevant = _condition(element.get("relevant"))
    if relevant is not None:
        stated["relevant"] = relevant

    if element.get("type") == "subform":
        # The subform block already says where its groups come from, so the
        # `choices` key would be the same fact spelled twice.
        stated["subform"] = _subform(element)
    else:
        choices = _choices(element)
        if choices is not None:
            stated["choices"] = choices

    store = element.get("store")
    if store:
        # A link element writes to a link table rather than to a column, which
        # is why a proposal names records instead of setting a value.
        stated["link"] = {
            "link_table": store.get("link_table"),
            "source_field": store.get("source_field"),
            "target_field": store.get("target_field"),
            "orientation": store.get("orientation"),
        }

    refusal = _refusal(element)
    if refusal:
        stated["accepts_suggestions"] = False
        stated["refused_because"] = refusal

    return stated


def build(config):
    """
    The contract for a deployment, as a JSON-serialisable dict.

    Every table that has a form is described, because "which of these may a
    proposal create" is a question about the suggestions format rather than
    about the config, and answering it here would mean core deciding that an
    `activity` is more proposable than a link row. The instructions in the
    handoff bundle say which tables a producer should target.
    """
    forms = config.get("forms") or {}
    default_forms = config.get("default_forms") or {}

    tables = {}
    for table_name, form_name in default_forms.items():
        form = forms.get(form_name)
        if not form:
            continue
        tables[table_name] = {
            "form": form_name,
            "elements": {
                element_id: element_contract(element)
                for element_id, element in (form.get("elements") or {}).items()
            },
        }

    return {
        "format": CONTRACT_FORMAT,
        "suggestions_format": SUGGESTIONS_FORMAT,
        "deployment": config.get("title"),
        "config_hash": config_hash(config),
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tables": tables,
    }


def dumps(config):
    """The contract as the bytes that go in the bundle."""
    return json.dumps(build(config), indent=2, sort_keys=False) + "\n"

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
SUGGESTIONS_FORMAT = "collaboratorium-suggestions/0.2"

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
            },
        }
    groups = {
        group_id: {
            field_id: {"type": field.get("type"), "label": field.get("label")}
            for field_id, field in (fields or {}).items()
            if isinstance(field, dict)
        }
        for group_id, fields in parameters.items()
    }
    return {"kind": "static", "groups": groups}


def _refusal(element):
    """
    Why the suggestions format will not carry a value for this element, or None.

    Both rules are read off the config rather than off a table name, so they
    hold for a deployment this exporter has never seen.
    """
    element_type = element.get("type")

    if element_type == "subform" and _VOCABULARY_KEYS.issubset(
            element.get("parameters") or {}):
        # A tag grouping, in this deployment. The groups are rows in another
        # table and their inner shape is a JSON blob in that row, so the
        # contract cannot state what a valid value looks like and the importer
        # cannot validate one. That the vocabulary is also a grouping judgement
        # a person should be making is the better reason, but this one is the
        # one the config can prove. See docs/agentic-ingest.md §3.0.
        return ("its groups come from a table rather than from the config, so "
                "neither this contract nor the importer can state or check a "
                "valid value")

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

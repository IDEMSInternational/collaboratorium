"""
snapshot.py
Current state, as a producer needs to read it.

A proposal has to link to records that already exist, must not re-create what
is already there, and must not re-propose what a human declined. All three need
the deployment's *current* contents, not just its shape, which is why the
handoff bundle carries more than the contract.

Two deliberate properties, both from docs/agentic-ingest.md §2.2 and §2.4:

**Latest version only, no tombstones.** The tables are append-only on
`(id, version)` and link removal inserts a `status='deleted'` row rather than
deleting one. Every reader therefore has to partition by id and take the top
version, and a reader that gets it wrong proposes links against superseded
rows. That read is `db.get_current_records` and `db.get_relation_links`, so the
snapshot is core's output and not an invitation to redo the query.

**Minimised, not gated.** The bundle leaves the deployment, so the lever is to
send less rather than to send it to fewer people — a role gate would protect
what the same signed-in user reads in the spreadsheet a click away. Values of
email-typed elements are omitted: a producer needs to *resolve* a person, which
a name and an id do, and never needs to contact one.
"""
from datetime import datetime, timezone

import yaml

from pantograph import contract
from pantograph.db import get_current_records, get_relation_links

SNAPSHOT_FORMAT = "collaboratorium-snapshot/1"

# Columns no producer has a use for. `version` and `timestamp` describe the row
# rather than the thing, and a proposal may never set either.
_ROW_BOOKKEEPING = ("version", "timestamp", "rn")


def _omitted_elements(config):
    """
    `table.element` for every value the snapshot withholds, read off the config.

    Derived rather than listed, so a deployment that adds a second address field
    is covered without a change here, and so the snapshot can state what it left
    out instead of silently differing from the contract.
    """
    forms = config.get("forms") or {}
    omitted = []
    for table_name, form_name in (config.get("default_forms") or {}).items():
        form = forms.get(form_name) or {}
        for element_id, element in (form.get("elements") or {}).items():
            if (element or {}).get("type") == "email":
                omitted.append(f"{table_name}.{element_id}")
    return sorted(omitted)


def _link_tables(config):
    """
    The link tables, with the pair of columns each one joins.

    A link table is recognised by having a form whose own table it is *and* two
    mappings in `links:` — which is how the config already distinguishes a
    column pointing at another table from a table that exists to join two.
    """
    found = {}
    for table_name, link_config in (config.get("links") or {}).items():
        mappings = (link_config or {}).get("mappings") or []
        if len(mappings) != 2:
            continue
        if table_name not in (config.get("tables") or {}):
            continue
        found[table_name] = [m["link_col"] for m in mappings]
    return found


def build(config):
    """Current contents, as a JSON/YAML-serialisable dict."""
    omitted = set(_omitted_elements(config))
    link_tables = _link_tables(config)

    records = {}
    for table_name in (config.get("default_forms") or {}):
        if table_name in link_tables:
            # Carried under `links`, as pairs, rather than twice.
            continue
        rows = []
        for row in get_current_records(table_name):
            kept = {
                column: value for column, value in row.items()
                if column not in _ROW_BOOKKEEPING
                and f"{table_name}.{column}" not in omitted
            }
            rows.append(kept)
        records[table_name] = rows

    links = {}
    for table_name, (source_col, target_col) in link_tables.items():
        frame = get_relation_links(table_name, source_col, target_col)
        # A half-written link — one end null — is dropped rather than exported.
        # It reads back from pandas as NaN, which is neither None nor an id, and
        # a producer cannot do anything with an edge that has one end.
        frame = frame.dropna(subset=[source_col, target_col])
        links[table_name] = [
            {source_col: int(row[source_col]), target_col: int(row[target_col])}
            for _, row in frame.iterrows()
        ]

    return {
        "format": SNAPSHOT_FORMAT,
        "config_hash": contract.config_hash(config),
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # Stated rather than merely absent: a producer comparing the snapshot
        # against the contract would otherwise read a withheld value as an
        # empty one, and an empty email is a thing it might try to fill in.
        "omitted_elements": sorted(omitted),
        "counts": {name: len(rows) for name, rows in records.items()},
        "records": records,
        "links": links,
    }


def dumps(config):
    """The snapshot as the bytes that go in the bundle."""
    return yaml.safe_dump(build(config), sort_keys=False, allow_unicode=True,
                          default_flow_style=False, width=100)

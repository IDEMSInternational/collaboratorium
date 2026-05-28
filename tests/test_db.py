import pytest
import sqlite3
import pandas as pd
import os
from datetime import datetime
import collaboratorium.db
from collaboratorium.db import (
    db_connect, 
    get_latest_record, 
    get_dropdown_options, 
    build_elements_from_db,
    init_db
)
from collaboratorium.config_parser import load_config


# --- Fixture for an isolated DB connection per test ---
@pytest.fixture(autouse=True)
def clean_db(monkeypatch):
    """Ensures every test runs against a fresh schema, avoiding WinError 32 collisions."""
    test_db_path = "test_unit_database.db"
    
    # Force collaboratorium to use our isolated test file instead of the live database.db
    monkeypatch.setattr(collaboratorium.db, "DB", test_db_path)
    
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except PermissionError:
            pass
            
    config = load_config("config.yaml")
    collaboratorium.db.init_db(config)
    
    yield config
    
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except PermissionError:
            pass

def _insert_mock_row(table, data):
    """Helper to simulate the exact insert behavior of form_gen.py."""
    conn = db_connect()
    cur = conn.cursor()
    cols = ", ".join([f'"{k}"' for k in data.keys()])
    placeholders = ", ".join(["?"] * len(data))
    cur.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})', list(data.values()))
    conn.commit()
    conn.close()

# =====================================================================
# TEST 1: Version Resolution & Soft Deletes
# =====================================================================
def test_get_latest_record_resolves_versions():
    """
    Edge Case: The DB holds 3 rows for ID=1. 
    It must return Version 3, and completely ignore Versions 1 and 2.
    """
    _insert_mock_row("people", {"id": 1, "version": 1, "name": "Alice Old", "status": "active"})
    _insert_mock_row("people", {"id": 1, "version": 2, "name": "Alice New", "status": "active"})
    
    record = get_latest_record("people", object_id=1)
    assert record["name"] == "Alice New"
    assert record["version"] == 2

def test_get_latest_record_handles_soft_deletes():
    """
    Edge Case: If the most recent version of a record is marked 'deleted',
    the system must treat the object as entirely non-existent.
    """
    _insert_mock_row("people", {"id": 2, "version": 1, "name": "Bob", "status": "active"})
    # Simulate a user clicking delete on the frontend
    _insert_mock_row("people", {"id": 2, "version": 2, "name": "Bob", "status": "deleted"})
    
    record = get_latest_record("people", object_id=2)
    assert record == {}, "Failed: Returned a soft-deleted record!"

# =====================================================================
# TEST 2: Foreign Key / Dropdown Option CTE Logic
# =====================================================================
def test_get_dropdown_options_cte_grouping():
    """
    Edge Case: get_dropdown_options uses a complex SQL CTE with ROW_NUMBER()
    OVER(PARTITION BY...). We must ensure it doesn't return duplicate dropdown
    entries when a record has multiple versions, and omits deleted records.
    """
    # Item 1: Multiple versions
    _insert_mock_row("initiatives", {"id": 10, "version": 1, "name": "Init A", "status": "active"})
    _insert_mock_row("initiatives", {"id": 10, "version": 2, "name": "Init A (Updated)", "status": "active"})
    
    # Item 2: Deleted
    _insert_mock_row("initiatives", {"id": 20, "version": 1, "name": "Init B", "status": "deleted"})
    
    # Item 3: Standard active
    _insert_mock_row("initiatives", {"id": 30, "version": 1, "name": "Init C", "status": "active"})

    options = get_dropdown_options("initiatives", "id", "name")
    
    assert len(options) == 2, "Failed: Did not properly filter out old versions or deleted rows."
    
    # Verify the label updated to the v2 name
    opt_10 = next(opt for opt in options if opt["value"] == 10)
    assert opt_10["label"] == "Init A (Updated)"

# =====================================================================
# TEST 3: Cytoscape Graph Building & Many-to-Many Links
# =====================================================================
def test_build_elements_filters_soft_deleted_edges(clean_db):
    """
    Edge Case: Cytoscape edges are built dynamically from many-to-many link tables.
    If a link between an Activity and Initiative is "deleted", the edge should
    not be rendered in the graph view.
    """
    config = clean_db
    
    # 1. Create nodes
    _insert_mock_row("activities", {"id": 1, "version": 1, "name": "Act 1", "status": "active"})
    _insert_mock_row("initiatives", {"id": 1, "version": 1, "name": "Init 1", "status": "active"})
    
    # 2. Create an active link between them
    _insert_mock_row("activity_initiative_links", {
        "id": 100, "version": 1, "activity_id": 1, "initiative_id": 1, "status": "active"
    })
    
    # Build graph elements
    elements_with_link = build_elements_from_db(config, include_deleted=False)
    
    # We expect 2 nodes and 1 edge
    edges_found = [e for e in elements_with_link if 'source' in e['data']]
    assert len(edges_found) == 1
    actual_nodes_on_edge = {edges_found[0]['data']['source'], edges_found[0]['data']['target']}
    assert actual_nodes_on_edge == {"activities-1", "initiatives-1"}
    
    # 3. Simulate a user removing the link via the frontend form
    _insert_mock_row("activity_initiative_links", {
        "id": 100, "version": 2, "activity_id": 1, "initiative_id": 1, "status": "deleted"
    })
    
    # Re-build graph elements
    elements_without_link = build_elements_from_db(config, include_deleted=False)
    edges_found_after_delete = [e for e in elements_without_link if 'source' in e['data']]
    
    # The edge should now be completely excluded from the graph
    assert len(edges_found_after_delete) == 0, "Failed: The graph rendered a soft-deleted many-to-many link!"
import sqlite3
from datetime import datetime
import os

DB = "analytics.db"

def analytics_connect():
    return sqlite3.connect(DB)

def init_db():
    existed = os.path.exists(DB)

    conn = analytics_connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        person_id INTEGER,
        requested_table TEXT,
        requested_id INTEGER
    );"""
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS view_analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        person_id INTEGER,
        view_id TEXT,
        target_entities TEXT,
        used_advanced_pipeline INTEGER,
        degree INTEGER,
        node_types TEXT,
        degree_types TEXT,
        degree_inout TEXT,
        start_date TEXT,
        end_date TEXT,
        node_count INTEGER
    );""")

    conn.commit()
    if not existed:
        print("Analysis db initialized.")
    conn.close()

def analytics_log(person_id, requested_table, requested_id):
    """
    Log an analytics event to the database.
    """
    conn = analytics_connect()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO analytics (person_id, requested_table, requested_id)
        VALUES (?, ?, ?);
    """, (person_id, requested_table, requested_id))

    conn.commit()
    conn.close()

def log_view_event(person_id, view_id, target_entities, used_advanced_pipeline, 
                   degree, node_types, degree_types, degree_inout, 
                   start_date, end_date, node_count):
    """
    Log a graph view interaction and its rich filtering parameters to the database.
    """
    if not person_id:
        return # Do not log if user is not authenticated
        
    conn = analytics_connect()
    cur = conn.cursor()

    # Safely serialize lists to comma-separated strings for easy logging
    targets_str = ",".join(target_entities) if target_entities else None
    node_types_str = ",".join(node_types) if node_types else None
    degree_types_str = ",".join(degree_types) if degree_types else None
    degree_inout_str = ",".join(degree_inout) if degree_inout else None

    cur.execute("""
        INSERT INTO view_analytics (
            person_id, view_id, target_entities, used_advanced_pipeline,
            degree, node_types, degree_types, degree_inout,
            start_date, end_date, node_count
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (person_id, view_id, targets_str, used_advanced_pipeline, 
          degree, node_types_str, degree_types_str, degree_inout_str, 
          start_date, end_date, node_count))

    conn.commit()
    conn.close()
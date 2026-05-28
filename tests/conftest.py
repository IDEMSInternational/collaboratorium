import pytest
import os
import sys
import threading
import sqlite3
from werkzeug.serving import make_server

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'collaboratorium')))

# 2. ISOLATE DATABASES BEFORE IMPORTING MAIN
import db
import analytics
import tools.analysis_report

TEST_DB = "test_database.db"
TEST_ANALYTICS_DB = "test_analytics.db"

db.DB = TEST_DB
analytics.DB = TEST_ANALYTICS_DB
tools.analysis_report.MAIN_DB = TEST_DB
tools.analysis_report.ANALYTICS_DB = TEST_ANALYTICS_DB

from main import app, config
from db import init_db
from analytics import init_db as init_analytics_db

class ServerThread(threading.Thread):
    def __init__(self, app, host='0.0.0.0', port=8055):
        threading.Thread.__init__(self)
        self.server = make_server(host, port, app.server)
        self.ctx = app.server.app_context()
        self.ctx.push()

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()

@pytest.fixture(scope="session", autouse=True)
def live_server():
    # Clean up previous test runs
    for f in [TEST_DB, TEST_ANALYTICS_DB, "database.db"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except PermissionError:
                pass
    
    # Initialize fresh test schemas
    init_db(config)
    init_analytics_db()
    
    # ---------------------------------------------------------
    # SEED ROBUST DUMMY DATA
    # ---------------------------------------------------------
    import datetime
    now = datetime.datetime.now().isoformat()
    
    conn = sqlite3.connect(TEST_DB)
    cur = conn.cursor()
    
    # 1. Seed a Test User
    cur.execute("""
        INSERT INTO people (id, version, name, email, status, timestamp, created_by) 
        VALUES (1, 1, 'Automated Tester', 'testrunner@idems.international', 'active', ?, 1)
    """, (now,))
    
    # 2. Seed Initiatives
    cur.execute("""
        INSERT INTO initiatives (id, version, name, status, timestamp, created_by, responsible_person) 
        VALUES (1, 1, 'Initiative: Solar', 'active', ?, 1, 1)
    """, (now,))
    cur.execute("""
        INSERT INTO initiatives (id, version, name, status, timestamp, created_by, responsible_person) 
        VALUES (2, 1, 'Initiative: Water', 'active', ?, 1, 1)
    """, (now,))
    
    # 3. Seed Activities
    cur.execute("""
        INSERT INTO activities (id, version, name, status, timestamp, created_by) 
        VALUES (1, 1, 'Activity: Build Panel', 'active', ?, 1)
    """, (now,))
    
    # 4. Seed Links
    cur.execute("""
        INSERT INTO activity_initiative_links (id, version, activity_id, initiative_id, status, timestamp, created_by) 
        VALUES (1, 1, 1, 1, 'active', ?, 1)
    """, (now,))
    
    conn.commit()
    conn.close()
    # ---------------------------------------------------------

    server = ServerThread(app, port=8055)
    server.start()
    
    yield 
    
    server.shutdown()
    for f in [TEST_DB, TEST_ANALYTICS_DB, "database.db"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except PermissionError:
                pass
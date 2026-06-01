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
    for f in [TEST_DB, TEST_ANALYTICS_DB]:
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
    
    # 1. Seed 5 People (ID 1 is the Automated Tester)
    cur.execute("INSERT INTO people (id, version, name, email, status, timestamp, created_by) VALUES (1, 1, 'Automated Tester', 'testrunner@idems.international', 'active', ?, 1)", (now,))
    for i in range(2, 6):
        cur.execute("INSERT INTO people (id, version, name, email, status, timestamp, created_by) VALUES (?, 1, ?, ?, 'active', ?, 1)", 
                    (i, f'Person {i}', f'person{i}@test.com', now))

    # 2. Seed 5 Initiatives
    for i in range(1, 6):
        cur.execute("INSERT INTO initiatives (id, version, name, status, timestamp, created_by, responsible_person) VALUES (?, 1, ?, 'active', ?, 1, ?)", 
                    (i, f'Initiative {i}', now, i))

    # 3. Seed 15 Activities
    for i in range(1, 16):
        cur.execute("INSERT INTO activities (id, version, name, status, timestamp, created_by) VALUES (?, 1, ?, 'active', ?, 1)", 
                    (i, f'Activity {i}', now))

    # 4. Link Data: 
    # Link Activities 1, 2, and 3 directly to the Automated Tester (User 1)
    for i in range(1, 4):
        cur.execute("INSERT INTO activity_people_links (id, version, activity_id, person_id, status, timestamp, created_by) VALUES (?, 1, ?, 1, 'active', ?, 1)", 
                    (i, i, now))
        
    # REALISTIC DISTRIBUTION: Link 3 unique activities to each of the 5 initiatives
    # Init 1 -> Acts 1,2,3 | Init 2 -> Acts 4,5,6 | Init 3 -> Acts 7,8,9 | etc.
    link_id = 1
    for init_id in range(1, 6):
        start_act = (init_id - 1) * 3 + 1
        for act_id in range(start_act, start_act + 3):
            cur.execute("INSERT INTO activity_initiative_links (id, version, activity_id, initiative_id, status, timestamp, created_by) VALUES (?, 1, ?, ?, 'active', ?, 1)", 
                        (link_id, act_id, init_id, now))
            link_id += 1
    
    conn.commit()
    conn.close()
    # ---------------------------------------------------------

    server = ServerThread(app, port=8055)
    server.start()
    
    yield 
    
    server.shutdown()
    for f in [TEST_DB, TEST_ANALYTICS_DB]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except PermissionError:
                pass
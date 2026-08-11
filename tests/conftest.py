import pytest
import os
import sys
import threading
import sqlite3
import shutil
import tempfile
import logging
from werkzeug.serving import make_server
logging.getLogger('werkzeug').setLevel(logging.ERROR)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# A directory of this run's own, so two suites running at once cannot read each
# other's rows. Relative names collided for anything sharing a working directory.
_DB_DIR = tempfile.mkdtemp(prefix="pantograph-tests-")
TEST_DB = os.path.join(_DB_DIR, "test_database.db")
TEST_ANALYTICS_DB = os.path.join(_DB_DIR, "test_analytics.db")

# Point the app at the test databases before anything reads them. Paths are
# resolved at call time now, so this no longer depends on import order.
from pantograph import settings
settings.configure(database_path=TEST_DB, analytics_path=TEST_ANALYTICS_DB)

from pantograph.app import create_app
from pantograph.config import load_config
from pantograph.db import init_db
from pantograph.analytics import init_db as init_analytics_db

config = load_config(settings.get_settings().config_path)
app = create_app()

@pytest.fixture(scope="session")
def base_url(live_server):
    """
    Overrides pytest-playwright's own fixture, which otherwise comes from
    --base-url. Naming it this means `page.goto("/")` resolves against the
    server this run started, so no test carries a port.
    """
    return live_server


@pytest.fixture(scope="session")
def app_config():
    """The merged deployment config the app under test was built from."""
    return config


@pytest.fixture(scope="session")
def dash_app():
    """The assembled app, for tests that inspect wiring rather than drive a page."""
    return app


class ServerThread(threading.Thread):
    def __init__(self, app, host="127.0.0.1", port=0):
        """
        Port 0 lets the OS pick a free one. A fixed port made the suite
        un-runnable twice at once anywhere on the machine: the second run bound
        nothing and its browser tests silently drove the first run's app, backed
        by a different database, failing differently every time.
        """
        threading.Thread.__init__(self)
        self.server = make_server(host, port, app.server)
        self.port = self.server.server_port
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

    server = ServerThread(app)
    server.start()

    yield f"http://127.0.0.1:{server.port}"

    server.shutdown()
    shutil.rmtree(_DB_DIR, ignore_errors=True)
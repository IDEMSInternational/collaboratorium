"""
Import: paste a suggestions file, see what it would do, and work the queue.

The same three steps the standalone `/import` pages offer, as a page of the app
so it has a nav button, shows how much is waiting, and opens a suggestion in the
editor already on screen rather than by way of a redirect. The routes stay: a
bookmark or a script that posts to them keeps working.

Nothing here writes a record. Staging puts proposals in the `suggestions`
table; a record exists only when a person confirms its fields in the editor and
saves. See docs/agentic-ingest.md §4.
"""
from pantograph.plugins import Plugin as BasePlugin

from pantograph_import.page import generate_layout, register_callbacks


class Plugin(BasePlugin):
    id = "import"
    label = "Import"

    # The suggestions table is made by init_db, not declared in config, so the
    # tables named here are the ones a suggestion's links resolve against.
    requires_tables = ("people", "initiatives", "activities")

    def layout(self, config):
        return generate_layout(config, self.id)

    def register(self, app, config):
        register_callbacks(app, config, self.id)

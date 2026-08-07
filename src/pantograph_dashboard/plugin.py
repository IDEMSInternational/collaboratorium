"""
The Collaboratorium dashboard: a feed of your recent work.

Deliberately specific. Unlike Explore, this page asks questions that only make
sense against a particular schema — "initiatives with no activity linked",
"activities not linked to any initiative", "people near your work" — and answers
them with SQL that names those tables outright. That is allowed: a finely tuned
plugin is the reason the plugin boundary exists. What it owes the deployment in
return is an honest declaration of what it assumes, so a config that does not
provide those tables fails at startup rather than at first click.
"""
import dash_bootstrap_components as dbc

from pantograph.plugins import Plugin as BasePlugin

from pantograph_dashboard.tab_dashboard import (
    generate_dashboard_layout,
    register_dashboard_callbacks,
)


class Plugin(BasePlugin):
    id = "dashboard"
    label = "Dashboard"

    requires_tables = (
        "activities",
        "initiatives",
        "people",
        "tag_groups",
        "activity_initiative_links",
        "activity_people_links",
    )

    def layout(self, config):
        return generate_dashboard_layout(config)

    def header_items(self, config):
        """
        The two most common things to add lead as solid buttons; core's
        catch-all "Add other…" stays a quiet link so three green buttons don't
        compete. The plus is text, not an icon: the Bootstrap Icons font isn't
        loaded (see TODO D).

        These live in the app header rather than on the page, but they belong to
        this plugin because it is what wires them up — and it hides them while
        an admin is viewing someone else's dashboard read-only.
        """
        return [
            dbc.Button("+ Activity", id="btn-add-activity", color="success",
                       className="me-2 fw-bold"),
            dbc.Button("+ Initiative", id="btn-add-initiative", color="success",
                       className="me-2 fw-bold"),
        ]

    def register(self, app, config):
        register_dashboard_callbacks(app, config, page_id=self.id)

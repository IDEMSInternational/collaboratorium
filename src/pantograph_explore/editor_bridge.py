"""
editor_bridge.py
Translates a tap on the network graph into a core editor request.

This lived in core's `load_form` until the editor gained a store to publish to,
which meant core named `cyto` — an Explore component — and carried the
node-versus-edge disambiguation below for a graph it otherwise knows nothing
about. Both belong here.
"""
from dash import Input, Output, ctx

from pantograph.editor import STORE_ID, edit_request, message_request


def _timestamp(tap):
    """
    Cytoscape stamps each tap. Used to break a tie between a node and an edge
    arriving together, and as the request token so each request is unique to the
    event that raised it (see pantograph.editor on why that is belt-and-braces
    rather than load-bearing).
    """
    try:
        return int(tap.get("timeStamp")) if tap and tap.get("timeStamp") is not None else None
    except (TypeError, ValueError):
        return None


def _node_is_newer(node, edge):
    node_ts, edge_ts = _timestamp(node), _timestamp(edge)
    if node_ts is None:
        return False
    if edge_ts is None:
        return True
    return node_ts >= edge_ts


def _request_for_node(tap_node):
    """A node id is "<table>-<id>"; anything else is not something we can edit."""
    try:
        table_name, id_str = tap_node["id"].split("-", 1)
        object_id = int(id_str)
    except (AttributeError, KeyError, TypeError, ValueError):
        return message_request("Invalid node clicked.", token=_timestamp(tap_node))
    return edit_request(table_name, object_id, token=_timestamp(tap_node))


def _request_for_edge(tap_edge):
    table_name = tap_edge.get("table_name")
    object_id = tap_edge.get("object_id")
    token = _timestamp(tap_edge)
    if not table_name or object_id is None:
        # Some edges are drawn from a column rather than a link table, so there
        # is no record behind them to open.
        return message_request(
            f"This edge ({tap_edge.get('label')}) is not editable.", token=token
        )
    return edit_request(table_name, object_id, token=token)


def register_editor_bridge_callbacks(app, config):
    @app.callback(
        Output(STORE_ID, "data", allow_duplicate=True),
        Input("cyto", "tapNodeData"),
        Input("cyto", "tapEdgeData"),
        prevent_initial_call=True,
    )
    def request_editor_from_graph(tap_node, tap_edge):
        # Which property changed is usually enough. Dash can dispatch both in
        # one batch, though, so fall back to the tap timestamps.
        triggered = {t["prop_id"] for t in ctx.triggered}
        node_fired = "cyto.tapNodeData" in triggered
        edge_fired = "cyto.tapEdgeData" in triggered

        if node_fired and edge_fired:
            node_fired = _node_is_newer(tap_node, tap_edge)
            edge_fired = not node_fired

        if node_fired and tap_node:
            return _request_for_node(tap_node)
        if edge_fired and tap_edge:
            return _request_for_edge(tap_edge)
        return None

from dash import html, dcc, Input, Output, State, ctx, ALL, no_update, MATCH
from datetime import datetime
from pantograph.db import db_connect, get_latest_entry
import json
import dash_bootstrap_components as dbc

from pantograph.analytics import analytics_log
from pantograph.auth import login_required
from pantograph.component_factory import component_for_element, register_subform_blocks, wrap_provenance
from pantograph import provenance, relevance, requirements


# ==============================================================
# DATABASE HELPERS
# ==============================================================


def _get_max_id_from_cursor(cur, table_name):
    """Helper to get max ID using an existing cursor."""
    cur.execute(f'SELECT MAX(id) FROM "{table_name}"')
    r = cur.fetchone()
    return int(r[0]) if r and r[0] is not None else 0


# ==============================================================
# FORM LAYOUT GENERATION
# ==============================================================


def generate_form_layout(form_name, forms_config, object_id=None, initial_values=None,
                         title=None, provenances=None):
    """
    Generate a Dash form layout from a form config.

    initial_values pre-populates an add form, keyed by element name and using the
    same shapes an edit form would load (so a links element takes a list of ids).

    provenances says where those values came from — {element_name: provenance
    record}, see pantograph.provenance. It is a parallel map rather than a
    wrapper around each value because several element types are already dict- or
    list-valued, and a value that might or might not be a `{"value": ...}` box
    would have to be unpicked in every one of them.

    title overrides the heading (e.g. "Add activity to <initiative>"). It's part
    of the form DOM, so it's set atomically when the form renders — no separate
    callback to race.
    """
    if object_id:
        record_data = get_latest_entry(form_name, forms_config, object_id)
    else:
        record_data = dict(initial_values or {})
    provenances = provenances or {}

    elements = []
    for element_name, element_def in forms_config[form_name].get("elements", {}).items():
        val = record_data.get(element_name) if record_data else None
        element_def = {**element_def, "element_id": element_name}
        component = component_for_element(element_def, form_name=form_name, value=val)
        # Wrapped inside the relevance container, so hiding an irrelevant
        # element hides the claim about where its value came from too.
        component = wrap_provenance(component, form_name, element_name,
                                    provenances.get(element_name))
        if element_def.get("relevant"):
            # Only conditional elements are wrapped, so nothing about an
            # existing deployment's DOM changes.
            component = relevance.wrap(component, form_name, element_name)
        elements.append(component)

    meta_hidden = []
    for element_name, element_def in forms_config[form_name].get("meta", {}).items():
        val = record_data.get(element_name) if record_data else None
        element_def = {"element_id": element_name, "type": "hidden"}
        meta_hidden.append(component_for_element(element_def, form_name=form_name, value=val))

    meta = html.Div([
        html.Details(
            [
                html.Summary(f"System Metadata Information"),
            ] + [html.Div(f"\t{key}: {record_data.get(key, None)}") for key in forms_config[form_name].get("meta", [])]
        ),
    ])

    heading = title or (
        f"Edit {forms_config[form_name]['label']}" if object_id
        else f"Add {forms_config[form_name]['label']}"
    )
    return html.Div([
        html.H3(heading, id="form-heading", className="mb-4 text-primary"),
        *meta_hidden,
        *elements,
        html.Div(meta, style={"marginTop": "25px", "marginBottom": "20px", "opacity": "0.7"}),
        html.Div([
            dbc.Button("Submit", id={"type": "submit", "form": form_name}, n_clicks=0, color="success", className="me-2 fw-bold"),
            dbc.Button("Cancel", id={"type": "cancel", "form": form_name}, n_clicks=0, color="secondary", outline=True),
        ], className="d-flex align-items-center mt-3"),
        html.Div(id={"type": "output", "form": form_name})
    ])


# ==============================================================
# CALLBACK REGISTRATION
# ==============================================================

def register_form_callbacks(app, config):
    register_click_callbacks(app, config)
    register_submit_callbacks(app, config.get("forms", {}))
    register_subform_blocks(app, config.get("forms", {}))
    provenance.register_provenance_callbacks(app)
    relevance.register_relevance_callbacks(app, config.get("forms", {}))
    requirements.register_required_callbacks(app, config.get("forms", {}))

def register_click_callbacks(app, config):
    forms_config = config.get("forms", {})

    @app.callback(
        Output("form-container", "children"),
        Input("table-selector", "value"),
        Input("editor-request", "data"),
        Input('url', 'hash'),
        State("current-person-id", "data"),
        Input("form-refresh", "data"),
        State("form-prefill", "data"),
    )
    @login_required
    def load_form(table_name, request, url_hash, person_id, refresh_signal, prefill):
        """
        Display a form based on what triggered: the Add selector, a URL hash
        link, or an editor-request published by a page.

        Core knows nothing about where a request came from. A page that wants to
        open the editor writes to the `editor-request` store; see
        `EDITOR_REQUEST` in pantograph.editor for the shape.
        """
        trigger = ctx.triggered[0].get('prop_id', '') if ctx.triggered else None

        if trigger == "form-refresh.data":
            return html.Div("Select a table or click an element to edit.")

        # 1. Hash Routing (from Report links and AG Grid Edit column)
        if trigger == 'url.hash' and url_hash:
            # url_hash comes in as "#edit/table/id"
            parts = url_hash.strip('#').split('/')
            if len(parts) == 3 and parts[0] == 'edit':
                tbl, obj_id = parts[1], parts[2]
                try:
                    return show_edit_form(tbl, obj_id, person_id)
                except Exception:
                    pass

        # If the table selector is the trigger, show the add form (explicit user choice)
        if trigger and trigger.startswith("table-selector"):
            if table_name:
                values, title, provenances = _prefill_for(table_name, prefill)
                return show_add_form(table_name, person_id, values, title, provenances)
            return "Select a table"

        if trigger and trigger.startswith("editor-request") and request:
            return _form_for_request(request, person_id)

        # No explicit trigger (initial or programmatic call): fall back to the
        # add form when a table is already selected. Gated on there being no
        # trigger at all, because a leftover table-selector value must not turn
        # an unrelated event — the hash being cleared as the editor closes —
        # into an add form for whatever was last selected.
        if not trigger and table_name:
            values, title, provenances = _prefill_for(table_name, prefill)
            return show_add_form(table_name, person_id, values, title, provenances)

        return html.Div("Select a table or click an element to edit.")

    def _form_for_request(request, person_id):
        if not isinstance(request, dict):
            return html.Div("Select a table or click an element to edit.")

        mode = request.get("mode")
        if mode == "message":
            # The requesting page decided this thing isn't editable and supplied
            # its own wording; core has no better one to offer.
            return html.P(request.get("text") or "This element is not editable.")
        if mode == "edit":
            return show_edit_form(request.get("table"), request.get("id"), person_id)
        if mode == "add":
            return show_add_form(
                request.get("table"), person_id,
                request.get("values") or None, request.get("title"),
                request.get("provenance") or None,
            )
        return html.Div("Select a table or click an element to edit.")


    def _prefill_for(table_name, prefill):
        """
        A prefill only applies to the table it was requested for, so a stale
        request can never leak into a different form. Returns
        (values, title, provenances).
        """
        if not isinstance(prefill, dict) or prefill.get("table") != table_name:
            return None, None, None
        return (prefill.get("values") or None, prefill.get("title"),
                prefill.get("provenance") or None)

    def show_add_form(table_name, person_id, initial_values=None, title=None,
                      provenances=None):
        if not table_name:
            return "Select a table"
        form_name = config["default_forms"][table_name]
        return login_required(generate_form_layout)(
            form_name, forms_config=forms_config, initial_values=initial_values,
            title=title, provenances=provenances,
        )


    def show_edit_form(table_name, object_id, person_id):
        try:
            object_id = int(object_id)
        except (ValueError, TypeError):
            return html.Div("Invalid record requested.")
        form_name = config["default_forms"].get(table_name, None)
        if not form_name:
            return html.Div(f"Error: Table '{table_name}' not in config['default_forms'].")

        analytics_log(person_id, table_name, object_id)
        return login_required(generate_form_layout)(form_name, forms_config=forms_config, object_id=object_id)

    @app.callback(
        [Output("editor-popup", "is_open", allow_duplicate=True),
        Output("add-dropdown-container", "style"),
        Output("table-selector", "value")],
        [Input("btn-add-element", "n_clicks"),
        Input("editor-request", "data"),
        Input("url", "hash"),
        Input({"type": "cancel", "form": ALL}, "n_clicks")],
        prevent_initial_call=True
    )
    def control_editor_flow(add_clicks, request, url_hash, cancel_clicks):
        trigger = ctx.triggered_id
        # Safely unpack pattern dict callback context assignments
        if isinstance(trigger, dict) and trigger.get("type") == "cancel":
            if any(clicks > 0 for clicks in cancel_clicks if clicks is not None):
                return False, no_update, no_update
        if trigger == "btn-add-element":
            return True, {"display": "block"}, None
        if trigger in ["editor-request", "url"]:
            if trigger == "url" and (not url_hash or "edit" not in url_hash):
                return no_update, no_update, no_update
            if trigger == "editor-request" and not request:
                return no_update, no_update, no_update
            return True, {"display": "none"}, no_update
        return no_update, no_update, no_update

    @app.callback(
        Output('url', 'hash', allow_duplicate=True),
        Input('editor-popup', 'is_open'),
        State('url', 'hash'),
        prevent_initial_call=True
    )
    def clear_hash_on_modal_close(is_open, current_hash):
        # Only clear the hash if the modal is actively closing AND the hash currently holds an edit route
        if not is_open and current_hash and 'edit' in current_hash:
            return ""
        
        return no_update

def register_submit_callbacks(app, forms_config):
    """Register one submit callback per form in the config."""
    for form_name, fc in forms_config.items():
        value_key_map = {
            "date": "date",
            "datetime": "date",
            "subform": "data",
            "table": "data",
        }
        
        input_ids = [{"type": "input", "form": form_name, "element": e_id} for e_id in fc["elements"].keys()]
        meta_ids = [{"type": "input", "form": form_name, "element": e_id} for e_id in fc["meta"].keys()]
        state_args = []
        for e_id, e_val in (fc["elements"] | fc["meta"]).items():
            i = {"type": "input", "form": form_name, "element": e_id}
            try:
                value_key = value_key_map.get(e_val['type'], "value")
            except KeyError:
                value_key = 'value'
            state_args.append(State(i, value_key))

        @app.callback(
            Output("out_msg", "children", allow_duplicate=True),
            Output('intermediary-loaded', 'data', allow_duplicate=True),
            Output("form-refresh", "data", allow_duplicate=True),
            Input({"type": "submit", "form": form_name}, "n_clicks"),
            State({"type": "link-input", "table": ALL, "source_col": ALL, "target_col": ALL}, "id"),
            State({"type": "link-input", "table": ALL, "source_col": ALL, "target_col": ALL}, "value"),
            State("current-person-id", "data"),
            # Matches nothing on a form whose values carry no provenance, which
            # is every form that existed before provenance did.
            State({"type": "provenance", "form": form_name, "element": ALL}, "data"),
            State({"type": "provenance", "form": form_name, "element": ALL}, "id"),
            *state_args,
            prevent_initial_call=True,
        )
        def handle_submit(n_clicks, link_ids, link_values, person_id,
                          provenance_data, provenance_ids, *values, _fc=fc):
            if n_clicks == 0:
                return None, no_update, no_update
            
            conn = db_connect()
            cur = conn.cursor()

            # Part 1: Handle the main object (Person, Initiative, etc.)
            element_ids = list(_fc["elements"].keys())
            data = dict(zip(element_ids + list(_fc["meta"].keys()), values))

            # An answer to a question that no longer applies is worse than no
            # answer -- a record claiming a legitimate-interest balancing test
            # when the basis has since become Consent would be actively
            # misleading. Recomputed here rather than trusting what the browser
            # had on screen. Nothing is lost: the schema is append-only, so the
            # previous answer stays in the record's history.
            for element_id in relevance.irrelevant_elements(_fc, data):
                data[element_id] = None

            # The disabled submit button is a courtesy to the user, not a gate:
            # the client posts this callback directly and can send what it likes.
            # A value nobody here has stood behind does not answer the question,
            # so the same check refuses it as refuses an empty one.
            provenances = provenance.by_element(provenance_ids, provenance_data)
            refusal = requirements.rejection_message(_fc, data, provenances=provenances)
            if refusal:
                conn.close()
                return html.Span(refusal, style={"color": "#dc3545"}), no_update, no_update

            object_id = data.get('id')
            if object_id == "":
                data["id"] = None
                object_id = None
            is_new_object = object_id is None
            
            out_msg = None
            if is_new_object:
                new_id = _get_max_id_from_cursor(cur, _fc["default_table"]) + 1
                object_id = new_id
                data['id'] = new_id
                data['version'] = 1
                data['status'] = 'active'
                out_msg = html.Span(f"✅ Created {_fc["default_table"]} record ID {data['id']}", style={"color": "green"})
            else:
                data['version'] = (data.get('version') or 0) + 1
                out_msg = html.Span(f"✅ Edited {_fc["default_table"]} record ID {data['id']}", style={"color": "green"})
            
            data['timestamp'] = datetime.now().isoformat()
            data['created_by'] = person_id

            cur.execute(f'pragma table_info("{_fc["default_table"]}")')
            r=cur.fetchall()
            cols_sql_ls = []
            placeholders = []
            vals = []
            for col in r:
                col_name = col[1]
                cols_sql_ls.append(col_name)
                placeholders.append("?")
                vals.append(data[col_name])
            cols_sql = ", ".join(cols_sql_ls)
            placeholders = ", ".join(placeholders)
            # Normalize Dash data types before SQL
            for i, v in enumerate(vals):
                if isinstance(v, list):
                    if len(v) == 0:
                        vals[i] = False
                    elif len(v) == 1 and isinstance(v[0], bool):
                        vals[i] = v[0]
                    else:
                        vals[i] = ",".join(map(str, v))
                elif isinstance(v, bool):
                    vals[i] = int(v)
            cur.execute(f'INSERT INTO "{_fc["default_table"]}" ({cols_sql}) VALUES ({placeholders})', vals)

            
            extra_elements = [element for element in data.keys() if element not in cols_sql_ls]
            # Part 2: Handle the Link Table Updates
            for element in extra_elements:
                if "store" in _fc["elements"][element].keys():
                    link_table = _fc["elements"][element]["store"]["link_table"]
                    source_col = _fc["elements"][element]["store"]['source_field']
                    target_col = _fc["elements"][element]["store"]['target_field']
                    
                    link_values = data[element]

                    newly_selected_ids = set(link_values if link_values else [])

                    sql_query = f'''
                    WITH RankedRow AS (
                        -- 1. Find all rows for this ID and rank them
                        --    (highest version gets rn = 1)
                        SELECT
                            id,
                            "{target_col}",
                            "status",
                            -- 1. Group rows by the link id
                            --    and rank them by version, newest = 1.
                            ROW_NUMBER() OVER(PARTITION BY id ORDER BY "version" DESC) as rn
                        FROM "{link_table}"
                        WHERE "{source_col}" = ?
                    )
                    -- 2. Select the top-ranked row (rn = 1)
                    --    only if its status is not 'deleted'
                    SELECT id, "{target_col}"
                    FROM RankedRow
                    WHERE rn = 1 AND "status" != 'deleted'
                    '''
                    cur.execute(sql_query, (object_id,))
                    current_links = {row[1]: row[0] for row in cur.fetchall()}
                    currently_linked_ids = set(current_links.keys())

                    ids_to_add = newly_selected_ids - currently_linked_ids
                    ids_to_remove = currently_linked_ids - newly_selected_ids

                    # Process removals: create a new version with status='deleted'
                    for target_id in ids_to_remove:
                        link_id = current_links[target_id]
                        cur.execute(f'SELECT * FROM "{link_table}" WHERE id = ? ORDER BY version DESC LIMIT 1', (link_id,))
                        cols = [d[0] for d in cur.description]
                        latest_link_data = dict(zip(cols, cur.fetchone()))
                        
                        latest_link_data['version'] += 1
                        latest_link_data['status'] = 'deleted'
                        latest_link_data['timestamp'] = datetime.now().isoformat()
                        
                        l_cols_sql = ", ".join([f'"{k}"' for k in latest_link_data.keys()])
                        l_placeholders = ", ".join(["?"] * len(latest_link_data))
                        cur.execute(f'INSERT INTO "{link_table}" ({l_cols_sql}) VALUES ({l_placeholders})', list(latest_link_data.values()))

                    # Process additions: create a new link record
                    for target_id in ids_to_add:
                        new_link_id = _get_max_id_from_cursor(cur, link_table) + 1
                        insert_data = {
                            'id': new_link_id,
                            'version': 1,
                            'timestamp': datetime.now().isoformat(),
                            'status': 'active',
                            source_col: object_id,
                            target_col: target_id,
                            'created_by': person_id
                        }

                        l_cols_sql = ", ".join([f'"{k}"' for k in insert_data.keys()])
                        l_placeholders = ", ".join(["?"] * len(insert_data))
                        cur.execute(f'INSERT INTO "{link_table}" ({l_cols_sql}) VALUES ({l_placeholders})', list(insert_data.values()))

            conn.commit()
            conn.close()

            return out_msg, datetime.now().isoformat(), int(datetime.now().timestamp()*1000)

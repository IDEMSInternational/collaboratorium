from dash import html, dcc, Input, Output, State, ctx, ALL, no_update, MATCH
from datetime import datetime
from pantograph.db import db_connect, get_latest_entry, get_latest_record, get_provenance, save_provenance
import json
import dash_bootstrap_components as dbc

from pantograph.analytics import analytics_log
from pantograph.auth import login_required
from pantograph.component_factory import component_for_element, register_subform_blocks, wrap_provenance
from pantograph import subforms
from pantograph import provenance, relevance, requirements
from pantograph.editor import parse_hash


def triggered_props():
    """
    Every prop that changed in this callback invocation, not just the first.

    `ctx.triggered_id` and `ctx.triggered[0]` name one trigger, and on a
    cold load there is never only one: the stores and the Location component
    all report their values in the same batch, so an empty `editor-request`
    routinely arrives ahead of the URL hash and wins. Someone following a
    link out of a report would then land on the dashboard with nothing open.
    Every callback that can be woken by the hash decides on the whole set.
    """
    return {t.get("prop_id", "") for t in (ctx.triggered or [])}


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


def _leaf_provenances(provenances, element_id):
    """
    The provenances belonging to one subform element, keyed by their full path.

    Kept whole rather than trimmed to the part after the element name, so the
    key a caller wrote is the key the renderer, the submit callback and the
    provenance table all see. One spelling end to end is what stops a leaf's
    origin being filed under a name nothing else uses.
    """
    found = {}
    for path, record in (provenances or {}).items():
        split = subforms.split_leaf(path)
        if split is not None and split[0] == element_id:
            found[path] = record
    return found


def _describe_previous(element_def, value):
    """
    A recorded value as one readable line for "Currently recorded: …".

    Link lists are shown by name, not id; a subform (tags, the grouped
    description) by its non-empty leaves; anything empty as "nothing".
    """
    if value in (None, "", [], {}):
        return "nothing"
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                value = parsed
        except ValueError:
            return value
    from_table = ((element_def.get("choices") or {}).get("from_table"))
    if isinstance(value, list):
        names = []
        for item in value:
            name = None
            if from_table and isinstance(item, int):
                conn = db_connect()
                try:
                    row = conn.execute(
                        f'SELECT name FROM "{from_table}" WHERE id = ? '
                        f'ORDER BY version DESC LIMIT 1', (item,)).fetchone()
                finally:
                    conn.close()
                name = row[0] if row else None
            names.append(str(name if name is not None else item))
        return ", ".join(names) or "nothing"
    if isinstance(value, dict):
        parts = []
        for group in value.values():
            fields = group if isinstance(group, dict) else {}
            for key, leaf in fields.items():
                if leaf in (None, "", []):
                    continue
                parts.append(f"{key}: " + (", ".join(map(str, leaf))
                                           if isinstance(leaf, list) else str(leaf)))
        return "; ".join(parts) or "nothing"
    return str(value)


def previous_values(form_name, forms_config, object_id, initial_values):
    """
    {element: description} of what the record holds for each element a proposal
    changes. Elements the proposal leaves as they are get no entry.
    """
    before = get_latest_entry(form_name, forms_config, object_id) or {}
    elements = forms_config[form_name].get("elements", {})
    shown = {}
    for element, proposed in (initial_values or {}).items():
        if element not in elements or before.get(element) == proposed:
            continue
        shown[element] = _describe_previous(elements[element], before.get(element))
    return shown


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
        previous = (previous_values(form_name, forms_config, object_id, initial_values)
                    if initial_values else {})
        if initial_values:
            # An edit form opened with *proposed* changes: the record as it
            # stands, with a caller's values laid over the elements it speaks
            # about. This is what lets an ingested suggestion against an
            # existing record be reviewed in the ordinary form — the reviewer
            # sees the proposal in place, marked unconfirmed, next to the values
            # it would replace. Elements the caller says nothing about keep what
            # is in the record, so a proposal cannot blank a field by omission.
            record_data = {**(record_data or {}), **initial_values}
        if provenances is None:
            # An edit form reopens the claim the record was saved with, so a
            # value nobody stood behind is still unconfirmed a year later. A
            # caller that passed its own provenances is describing values it
            # also passed, and is not overruled by what is on disk.
            provenances = get_provenance(forms_config[form_name]["default_table"],
                                         object_id, record_data.get("version"))
    else:
        record_data = dict(initial_values or {})
        previous = {}
    provenances = provenances or {}

    elements = []
    for element_name, element_def in forms_config[form_name].get("elements", {}).items():
        val = record_data.get(element_name) if record_data else None
        element_def = {**element_def, "element_id": element_name}
        # A subform's fields are addressed by path — `description.1.description`
        # — and rendered by a callback rather than here, so theirs travel in a
        # store the callback reads. Everything else is keyed by element name.
        component = component_for_element(
            element_def, form_name=form_name, value=val,
            leaf_provenances=_leaf_provenances(provenances, element_name))
        # Wrapped inside the relevance container, so hiding an irrelevant
        # element hides the claim about where its value came from too.
        component = wrap_provenance(component, form_name, element_name,
                                    provenances.get(element_name),
                                    previous=previous.get(element_name))
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
        triggers = triggered_props()
        # One name for the common case of a single trigger; `triggers` for the
        # decisions that have to hold when the batch carries several.
        trigger = next(iter(triggers), None) if len(triggers) == 1 else None

        if triggers == {"form-refresh.data"}:
            return html.Div("Select a table or click an element to edit.")

        # 1. Hash Routing (from Report links and AG Grid Edit column)
        if 'url.hash' in triggers and url_hash:
            # A link is all a markdown report or a grid cell can offer, so the
            # routes it writes are parsed into the same requests a page would
            # publish to the store. See pantograph.editor.parse_hash.
            routed = parse_hash(url_hash)
            if routed:
                try:
                    return _form_for_request(routed, person_id)
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
            table = request.get("table")
            values = _shaped_values(table, request.get("values") or None)
            return show_add_form(
                table, person_id, values,
                request.get("title") or _title_for_values(table, values),
                request.get("provenance") or None,
            )
        if mode == "suggestion":
            return show_suggestion_form(request.get("id"), person_id)
        return html.Div("Select a table or click an element to edit.")

    def show_suggestion_form(suggestion_id, person_id):
        """
        A staged proposal, in the ordinary form, with every value it supplies
        marked as not yet stood behind.

        This is the whole of "confirming is the write": nothing here saves
        anything. The reviewer gets the normal add or edit form, the proposal's
        values are already in it, and the machinery that shipped with
        provenance does the rest — the values render amber and dashed, they do
        not satisfy `required:`, and a save that slips an unconfirmed required
        answer past the disabled button is refused outright.
        """
        from pantograph import staging

        item = staging.get(suggestion_id) if suggestion_id is not None else None
        if not item:
            return html.Div("That suggestion is no longer in the queue.")
        if item["state"] != staging.PENDING:
            return html.Div(
                f"That suggestion was already {item['state']}.")

        table = item["table"]
        # Remembered here, not only where the queue hands the form over, so a
        # pasted or bookmarked #suggest link marks the suggestion answered when
        # it is saved, as the queue's Open button does. Otherwise the record is
        # created and its suggestion stays pending, and anything that was
        # waiting on it stays unlinkable.
        try:
            from flask import session
            session["reviewing_suggestion"] = (suggestion_id, table)
        except RuntimeError:
            pass
        values, provenances = staging.form_inputs(item)
        if item["action"] == "update" and item["target_id"]:
            form_name = config["default_forms"].get(table)
            if not form_name:
                return html.Div(f"Error: no form for '{table}'.")
            return login_required(generate_form_layout)(
                form_name, forms_config=forms_config,
                object_id=item["target_id"], initial_values=values,
                title=f"Proposed changes to {item['name']}",
                provenances=provenances,
            )
        return show_add_form(
            table, person_id, _shaped_values(table, values),
            f"Suggested {table[:-1] if table.endswith('s') else table}"
            + (f" — from {item['subject']}" if item.get("subject") else ""),
            provenances,
        )


    # ----------------------------------------------------------
    # Making a routed add form say what it is
    # ----------------------------------------------------------
    # A route carries ids and element names, because that is all a URL can
    # carry without going stale. Everything else a useful form needs is already
    # in forms config, so it is read here rather than restated in the link.

    def _element_def(table_name, element):
        form_name = config.get("default_forms", {}).get(table_name)
        if not form_name:
            return None
        return forms_config.get(form_name, {}).get("elements", {}).get(element)

    def _shaped_values(table_name, values):
        """
        Narrow a routed list to a scalar where the element it names holds one.

        Routes always arrive as lists, since a links element loads one. Pointing
        a route at a single-valued element is a config mistake rather than a
        shape to support, but it should open a form with the value set, not one
        with a list where a number goes.
        """
        if not isinstance(values, dict):
            return values
        shaped = {}
        for element, value in values.items():
            element_def = _element_def(table_name, element) or {}
            multiple = element_def.get("type") == "select_multiple"
            if not multiple and isinstance(value, list) and len(value) == 1:
                shaped[element] = value[0]
            else:
                shaped[element] = value
        return shaped

    def _title_for_values(table_name, values):
        """
        "Add Activities to Water Access" — the heading, read off the record the
        new one will be linked to.

        Only for a form prefilled with exactly one link, which is what a route
        produces; a caller filling several elements knows better than this does
        what the form is for, and passes its own title. Returns None when the
        record or its label cannot be found, so the generic "Add <label>"
        heading stands rather than a half-built one.

        The label is the form's own, plural as the app's other headings are
        ("Add Activities"), rather than a guess at a singular.
        """
        if not isinstance(values, dict) or len(values) != 1:
            return None
        (element, value), = values.items()
        object_id = value[0] if isinstance(value, list) and len(value) == 1 else value
        if not isinstance(object_id, int):
            return None

        parameters = (_element_def(table_name, element) or {}).get("parameters") or {}
        source_table, label_column = parameters.get("source_table"), parameters.get("label_column")
        if not source_table or not label_column:
            return None
        try:
            record = get_latest_record(source_table, object_id)
        except Exception:
            return None
        name = (record or {}).get(label_column)
        if not name:
            return None

        form_name = config.get("default_forms", {}).get(table_name)
        label = forms_config.get(form_name, {}).get("label", table_name)
        return f"Add {label} to {name}"

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
        triggers = triggered_props()
        trigger = ctx.triggered_id
        # Safely unpack pattern dict callback context assignments
        if isinstance(trigger, dict) and trigger.get("type") == "cancel":
            if any(clicks > 0 for clicks in cancel_clicks if clicks is not None):
                return False, no_update, no_update
        if "btn-add-element.n_clicks" in triggers:
            return True, {"display": "block"}, None
        # Asked of the router rather than matched as a substring: an add
        # route has to open the editor too, and the hash being cleared as
        # the editor closes must not reopen it.
        if "url.hash" in triggers and parse_hash(url_hash):
            return True, {"display": "none"}, no_update
        if "editor-request.data" in triggers and request:
            return True, {"display": "none"}, no_update
        return no_update, no_update, no_update

    @app.callback(
        Output('url', 'hash', allow_duplicate=True),
        Input('editor-popup', 'is_open'),
        State('url', 'hash'),
        prevent_initial_call=True
    )
    def clear_hash_on_modal_close(is_open, current_hash):
        # Only clear the hash if the modal is actively closing AND the hash
        # currently holds a route this editor opened — an add route as much as
        # an edit one, or the next click on the same link would be a no-op.
        if not is_open and parse_hash(current_hash) is not None:
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

            provenances = provenance.by_element(provenance_ids, provenance_data)

            # An answer to a question that no longer applies is worse than no
            # answer -- a record claiming a legitimate-interest balancing test
            # when the basis has since become Consent would be actively
            # misleading. Recomputed here rather than trusting what the browser
            # had on screen. Nothing is lost: the schema is append-only, so the
            # previous answer stays in the record's history.
            for element_id in relevance.irrelevant_elements(_fc, data):
                data[element_id] = None
                # A claim about where an answer came from cannot outlive the
                # answer it describes.
                provenances.pop(element_id, None)

            # The disabled submit button is a courtesy to the user, not a gate:
            # the client posts this callback directly and can send what it likes.
            # A value nobody here has stood behind does not answer the question,
            # so the same check refuses it as refuses an empty one.
            refusal = requirements.rejection_message(_fc, data, provenances=provenances)
            if refusal:
                conn.close()
                return html.Span(refusal, style={"color": "#dc3545"}), no_update, no_update

            object_id = data.get('id')
            if object_id == "":
                data["id"] = None
                object_id = None
            is_new_object = object_id is None

            # Read before anything is written, so it is the version being
            # replaced rather than the one about to be inserted.
            previous_values = (None if is_new_object
                               else get_latest_record(_fc["default_table"], object_id))

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
                value = data[col_name]
                # An emptied group stays on the page so it can be filled again,
                # but is not stored.
                if _fc["elements"].get(col_name, {}).get("type") == "subform":
                    value = subforms.prune_empty_groups(value)
                vals.append(value)
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
                elif isinstance(v, dict):
                    # A subform's value is stored as JSON text. It arrives as a
                    # mapping when the form was opened with one, as a staged
                    # suggestion's tags are, and has not been touched since.
                    vals[i] = json.dumps(v)
            cur.execute(f'INSERT INTO "{_fc["default_table"]}" ({cols_sql}) VALUES ({placeholders})', vals)

            # Same cursor, so the row and where its values came from commit
            # together. Keyed on the version just written, which is what makes
            # the record and its provenance one immutable pair.
            save_provenance(
                cur, _fc["default_table"], object_id, data['version'],
                provenance.surviving_edits(provenances, previous_values, data),
            )

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

            # If this save is a person confirming a staged suggestion, that
            # suggestion is now answered. Done after the commit and on its own
            # connection, because a staging bookkeeping failure must never roll
            # back a record the user has just signed for.
            from pantograph import staging
            staging.note_saved(_fc["default_table"], object_id)

            return out_msg, datetime.now().isoformat(), int(datetime.now().timestamp()*1000)

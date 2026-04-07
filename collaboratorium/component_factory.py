from dash import html, dcc, Input, Output, State, ctx, ALL, no_update, MATCH, dash_table
from datetime import datetime
import json
from visual_customization import dcl
from db import get_dropdown_options


# ==============================================================
# COMPONENT FACTORY
# ==============================================================


def component_for_element(element_config, form_name, value=None):
    """Map element type from YAML to Dash component"""
    element_type = element_config.get("type")
    label = element_config.get("label", element_config["element_id"])
    appearance = element_config.get("appearance", None)

    input_type_mapping = {
        "integer": "number",
        "decimal": "number",
        "email": "email",
        "url": "url",
        "tel": "tel",
        "hidden": "hidden",
    }
    # --- TEXT / NUMBER / DATE ---
    if element_type in ("text", "string", "integer", "decimal", "email", "url", "tel"):
        if appearance == "multiline":
            return html.Div(
                [
                    html.Label(label),
                    dcl.Textarea(
                        id={"type": "input", "form": form_name, "element": element_config["element_id"]},
                        style={'width': '100%'},
                        value=value or "",
                    ),
                ]
            )
        return html.Div(
            [
                html.Label(label),
                dcc.Input(
                    id={"type": "input", "form": form_name, "element": element_config["element_id"]},
                    type=input_type_mapping.get(element_type, "text"),
                    value=value or "",
                    style={'width': '100%'},
                ),
            ]
        )
    
    # --- hidden ---
    elif element_type == "hidden":
        return dcc.Input(
                    id={"type": "input", "form": form_name, "element": element_config["element_id"]},
                    type="hidden",
                    value=value or "",
                )

    # --- datetime ---
    elif element_type == "date":
        return html.Div(
            [
                html.Label(label),
                dcc.DatePickerSingle(
                    id={"type": "input", "form": form_name, "element": element_config["element_id"]},
                    date=value or None,
                ),
            ]
        )
    
    # --- boolean ---
    elif element_type == "boolean":
        # Checklist expects a list for `value` — populate accordingly
        checklist_value = [True] if value else []
        return dcc.Checklist(
            id={"type": "input", "form": form_name, "element": element_config["element_id"]},
            options=[{"label": "True", "value": True}],
            value=checklist_value
        )

    # --- SELECT SINGLE ---
    elif element_type == "select_one":
        if 'list_name' in element_config:
            options = element_config[element_config['list_name']]
        else:
            options = get_dropdown_options(
                element_config["parameters"]["source_table"],
                element_config["parameters"]["value_column"],
                element_config["parameters"]["label_column"],
            )
        return html.Div(
            [
                html.Label(label),
                dcc.Dropdown(
                    id={"type": "input", "form": form_name, "element": element_config["element_id"]},
                    options=options,
                    value=value,
                    clearable=True,
                ),
            ]
        )

    # --- SELECT MULTIPLE ---
    elif element_type == "select_multiple":
        if 'list_name' in element_config:
            options = element_config[element_config['list_name']]
        else:
            options = get_dropdown_options(
                element_config["parameters"]["source_table"],
                element_config["parameters"]["value_column"],
                element_config["parameters"]["label_column"],
            )
        return html.Div(
            [
                html.Label(label),
                dcc.Dropdown(
                    id={"type": "input", "form": form_name, "element": element_config["element_id"]},
                    options=options,
                    value=value or [],
                    multi=True,
                    clearable=True,
                ),
            ]
        )

    # --- Table ---
    elif element_type == "table":
        if 'columns' in element_config:
            columns = element_config['columns']
        else:
            columns = []

        empty_row = {c['id']: None for c in columns}
        if value is None:
            value = [empty_row]
        if value[-1] != empty_row:
            value.append(empty_row) # always new row
        if 'appearance' not in element_config.keys():
            return html.Div(
                [
                    html.Label(label),
                    dash_table.DataTable(
                        id={"type": "input", "form": form_name, "element": element_config["element_id"]},
                        columns=columns,
                        data=value,
                        row_deletable=True,
                        editable=True,
                        style_cell={'textAlign': 'left'},
                        style_header={'fontWeight': 'bold'}
                    ),
                ])
        elif element_config['appearance'] == 'markdown':
            markdown_str = '\n'.join([element_config['rowfmt'].format(**d) for d in value if d != empty_row])
            return html.Div(
                [
                    html.Label(label),
                    dcc.Markdown(markdown_str, link_target="_blank"),
                    html.Details(
                [
                    html.Summary(f'Modify {label}'),
                    dash_table.DataTable(
                        id={"type": "input", "form": form_name, "element": element_config["element_id"]},
                        columns=columns,
                        data=value,
                        row_deletable=True,
                        editable=True,
                        style_cell={'textAlign': 'left'},
                        style_header={'fontWeight': 'bold'}
                    ),
                ],
                    ),
                ])


    # --- Subform ---
    elif element_type == "subform":
        subform_block = html.Div([
            html.Div(id={"type": "subform", "form": form_name, "element": element_config["element_id"]}),
            dcc.Store(id={"type": "input", "form": form_name, "element": element_config["element_id"]},
                  data=value)
            ],)
        return subform_block

    # --- NextCloud Document ---
    elif element_type == "nextcloud_doc":
        nextcloud_block = html.Div([
            html.Label(label),
            # Configuration Store (holds NextCloud parameters from tag group)
            dcc.Store(
                id={"type": "nextcloud_config", "form": form_name, "element": element_config["element_id"]},
                data=value or {}
            ),
            # Button to create/open document
            html.Button(
                "Create/Open Report",
                id={"type": "nextcloud_button", "form": form_name, "element": element_config["element_id"]},
                n_clicks=0,
                style={
                    'padding': '10px 15px',
                    'backgroundColor': '#007bff',
                    'color': 'white',
                    'border': 'none',
                    'borderRadius': '4px',
                    'cursor': 'pointer',
                    'marginRight': '10px'
                }
            ),
            # Hidden input to store the resulting file path
            dcc.Input(
                id={"type": "nextcloud_file_path", "form": form_name, "element": element_config["element_id"]},
                type="hidden",
                value=value or ""
            ),
            # Status/output div for messages and links
            html.Div(
                id={"type": "nextcloud_output", "form": form_name, "element": element_config["element_id"]},
                style={
                    'marginTop': '10px',
                    'padding': '10px',
                    'borderRadius': '4px',
                    'backgroundColor': '#f8f9fa',
                    'minHeight': '40px'
                }
            )
        ], style={'margin': '15px 0', 'padding': '15px', 'border': '1px solid #dee2e6', 'borderRadius': '4px'})
        
        return nextcloud_block

    # --- NextCloud Attachments (Table + Document Creation) ---
    elif element_type == "nextcloud_attachments":
        if 'columns' in element_config:
            columns = element_config['columns']
        else:
            # Default columns for attachments
            columns = [
                {'name': 'File Name', 'id': 'name'},
                {'name': 'URL', 'id': 'url'},
            ]
        
        empty_row = {c['id']: None for c in columns}
        if value is None:
            value = [empty_row]
        if value and value[-1] != empty_row:
            value.append(empty_row)  # always new row for manual entry
        
        # Build the attachments block with button and status
        attachments_children = [
            html.Label(label),
            # Configuration Store (holds NextCloud parameters)
            dcc.Store(
                id={"type": "nextcloud_config", "form": form_name, "element": element_config["element_id"]},
                data=element_config.get('nextcloud_config', {})
            ),
            # Button to create new NextCloud document
            html.Div([
                html.Button(
                    "➕ Create New Document",
                    id={"type": "nextcloud_button", "form": form_name, "element": element_config["element_id"]},
                    n_clicks=0,
                    style={
                        'padding': '8px 12px',
                        'backgroundColor': '#28a745',
                        'color': 'white',
                        'border': 'none',
                        'borderRadius': '4px',
                        'cursor': 'pointer',
                        'marginBottom': '10px',
                        'fontSize': '14px'
                    }
                ),
                html.Div(
                    id={"type": "nextcloud_output", "form": form_name, "element": element_config["element_id"]},
                    style={
                        'display': 'inline-block',
                        'marginLeft': '10px',
                        'padding': '5px 10px',
                        'fontSize': '12px',
                        'borderRadius': '4px'
                    }
                )
            ], style={'marginBottom': '10px'}),
            html.Div(
                "Tip: Click 'Create New Document' to create a document in NextCloud. The URL will be automatically added to the table below. You can delete documents from the list or save the form to persist changes.",
                style={
                    'fontSize': '12px',
                    'color': '#666',
                    'marginBottom': '10px',
                    'padding': '8px',
                    'backgroundColor': '#f0f0f0',
                    'borderRadius': '4px'
                }
            ),
        ]
        
        # Add markdown appearance if configured
        if element_config.get('appearance') == 'markdown' and 'rowfmt' in element_config:
            markdown_str = '\n'.join([element_config['rowfmt'].format(**d) for d in value if d != empty_row])
            attachments_children.append(dcc.Markdown(markdown_str, link_target="_blank"))
            attachments_children.append(
                html.Details([
                    html.Summary(f'Modify {label}'),
                    dash_table.DataTable(
                        id={"type": "input", "form": form_name, "element": element_config["element_id"]},
                        columns=columns,
                        data=value,
                        row_deletable=True,
                        editable=True,
                        style_cell={'textAlign': 'left'},
                        style_header={'fontWeight': 'bold'},
                        style_data_conditional=[
                            {
                                'if': {'row_index': 'odd'},
                                'backgroundColor': '#f9f9f9'
                            }
                        ]
                    ),
                ])
            )
        elif element_config.get('appearance') == 'links':
            list_items = []
            
            for d in value:
                if d == empty_row or not d.get('url'):
                    continue
                    
                url = d['url']
                name = d.get('name', 'Unnamed Document')
                
                # CSS to make buttons look like links and truncate long text smoothly
                link_style = {
                    "background": "none", "border": "none", "color": "#007bff", 
                    "textDecoration": "underline", "cursor": "pointer", "padding": "0", 
                    "font": "inherit", "textAlign": "left",
                    "maxWidth": "250px",           # Prevents it from pushing the layout
                    "overflow": "hidden", 
                    "textOverflow": "ellipsis",    # Adds the '...'
                    "whiteSpace": "nowrap",
                    "display": "inline-block",
                    "verticalAlign": "bottom"
                }
                
                # Check if it's an internal NextCloud URL
                if "embedded" in url: # "cloud.condy.xyz" in url:
                    # Renders as a button that triggers the Python callback -> Modal
                    action_element = html.Button(
                        name, 
                        id={"type": "open-doc-btn", "url": url}, 
                        n_clicks=0,
                        style=link_style,
                        title=name # Hover tooltip
                    )
                else:
                    # Renders as a standard HTML link that bypasses Python -> New Tab
                    action_element = html.A(
                        name,
                        href=url,
                        target="_blank",
                        style=link_style,
                        title=name # Hover tooltip
                    )
                
                list_items.append(html.Li(action_element, style={"marginBottom": "4px"}))

            attachments_children.append(html.Ul(list_items, style={"paddingLeft": "20px"}))

            attachments_children.append(
                html.Details([
                    html.Summary(f'Modify {label}'),
                    dash_table.DataTable(
                        id={"type": "input", "form": form_name, "element": element_config["element_id"]},
                        columns=columns,
                        data=value,
                        row_deletable=True,
                        editable=True,
                        style_cell={'textAlign': 'left'},
                        style_header={'fontWeight': 'bold'},
                        style_data_conditional=[
                            {
                                'if': {'row_index': 'odd'},
                                'backgroundColor': '#f9f9f9'
                            }
                        ]
                    ),
                ])
            )
        else:
            # Standard table view
            attachments_children.append(
                dash_table.DataTable(
                    id={"type": "input", "form": form_name, "element": element_config["element_id"]},
                    columns=columns,
                    data=value,
                    row_deletable=True,
                    editable=True,
                    style_cell={'textAlign': 'left'},
                    style_header={'fontWeight': 'bold'},
                    style_data_conditional=[
                        {
                            'if': {'row_index': 'odd'},
                            'backgroundColor': '#f9f9f9'
                        }
                    ]
                )
            )
        
        # Hidden input to track newly created document path
        attachments_children.append(
            dcc.Input(
                id={"type": "nextcloud_file_path", "form": form_name, "element": element_config["element_id"]},
                type="hidden",
                value=""
            )
        )
        
        attachments_block = html.Div(
            attachments_children,
            style={'margin': '15px 0', 'padding': '15px', 'border': '1px solid #dee2e6', 'borderRadius': '4px'}
        )
        
        return attachments_block
        

    # --- DEFAULT FALLBACK ---
    return html.Div([
        html.Label(label), 
        html.Div("Unsupported element type", id={"type": "input", "form": form_name, "element": element_config["element_id"]})
    ])

def combine_lists_with_nones(lists):
    if not lists:
        return []

    # Determine the length of the lists (assuming all have the same length)
    list_length = len(lists[0])
    combined_list = [None] * list_length  # Initialize with None or a default value

    for i in range(list_length):
        for current_list in lists:
            if current_list[i] is not None:
                combined_list[i] = current_list[i]
                break  # Move to the next index once a non-None value is found
    return combined_list


def register_subform_blocks(app, forms_config):
    """Register callbacks per subform in the config."""
    for form_name, fc in forms_config.items():

        state_args = []
        for e_id, e_val in fc["elements"].items():
            if e_val['type'] != 'subform':
                continue
            element_config = dict(element_id=e_id, **e_val)
            
            subform_name = form_name+'-'+element_config["element_id"]
            @app.callback(
                Output({"type": "subform", "form": form_name, "element": element_config["element_id"]}, "children"),
                Input({"type": "input", "form": form_name, "element": element_config["element_id"]}, "data"),
            )
            def call_gen_subform_block(value, _element_config = element_config, _form_name = form_name):
                return generate_subform_block(_element_config, _form_name, value)
            

            @app.callback(
                Output({"type": "input", "form": form_name, "element": element_config["element_id"]}, "data"),
                State({"type": "input", "form": form_name, "element": element_config["element_id"]}, "data"),
                Input({"type": "input", "form": subform_name, "element": ALL}, "value"),
                Input({"type": "input", "form": subform_name, "element": ALL}, "date"),
                Input({"type": "input", "form": subform_name, "element": ALL}, "data"),
            )
            def handle_subform_block(state, values, date, data, _element_config = element_config, _form_name = form_name):
                if ctx.triggered_id is None:
                    return state

                input_keys = [i['id']['element'] for i in ctx.inputs_list[0]]
                combined_values = combine_lists_with_nones([values, date, data])
                flat_input_dict = dict(zip(input_keys, combined_values))
                input_dict = {}
                for key, val in flat_input_dict.items():
                    if '|' in key:
                        parts = key.split('|')
                        assert(len(parts)==2)
                        if parts[0] not in input_dict.keys():
                            input_dict[parts[0]] = {}
                        input_dict[parts[0]][parts[1]] = val
                    else:
                        input_dict[key] = val

                if input_keys == ['failsafe']:
                    return None

                if input_dict.get('subform_selector', None) is not None:
                    subform_key_values = get_dropdown_options(
                        element_config["parameters"]["source_table"],
                        element_config["parameters"]["value_column"],
                        'key_values',
                    )
                    for subform in subform_key_values:
                        if subform['value'] == input_dict['subform_selector']:
                            input_dict[str(subform['value'])] = {}
                            e_cfg = json.loads(subform['label'])
                            for key in e_cfg.keys():
                                input_dict[str(subform['value'])][key] = None

                if 'subform_selector' in input_dict.keys():
                    auto_keep = input_dict.pop('subform_selector')
                else:
                    auto_keep = None
                try:
                    new_state = json.loads(state) if state not in [None, ''] else {}
                    new_state.update(input_dict)
                except:
                    new_state = input_dict


                for key in list(new_state.keys()):
                    keep=False
                    if type(new_state[key]) is dict:
                        for key2 in new_state[key].keys():
                            if new_state[key][key2] not in [None, '', []]:
                                keep = True
                    elif new_state[key] not in [None, '', []]:
                        keep = True
                    if key == str(auto_keep):
                        keep = True
                    if not keep:
                        new_state.pop(key)

                return json.dumps(new_state, indent=2)
            

def failsafe_div(label, subform_name, value):
    return html.Div(
        [
            html.Label(label+' FAILSAFE: malformed subform data'),
            html.Label('delete the string and add relavant subforms to replace the data'),
            component_for_element(
                element_config=dict(element_id=label, type='string'),
                form_name=subform_name,
                value=value
            ),            
        ], style={'backgroundColor': 'red', 'padding': '10px'}
    )

def generate_subform_block(element_config, form_name, value=None):
    label = element_config.get("label", element_config["element_id"])
    subform_name = form_name+'-'+element_config["element_id"]

    if {"source_table", "value_column", "label_column"}.issubset(set(element_config["parameters"].keys())):
        is_dynamic_form = True
    else:
        is_dynamic_form = False

    failsafe = False
    try:
        value = json.loads(value) if value else {}
    except json.decoder.JSONDecodeError:
        failsafe = True

    if type(value) is not dict:
        failsafe = True
    
    elements = []
    if is_dynamic_form:
        if failsafe:
            return failsafe_div(label, subform_name, value)
        elements = generate_dynamic_subform_elements(element_config, form_name, value)
    else:
        if failsafe or value == {}:
            failsafe_element_found = False if value != {} else True
            dummy_value = {}
            for group_id, subform in element_config['parameters'].items():
                dummy_value[group_id] = {}
                for key, val in element_config['parameters'][group_id].items():
                    if val['type'] == 'string' and not failsafe_element_found:
                        dummy_value[group_id][key] = value
                        failsafe_element_found = True
                    else:
                        dummy_value[group_id][key] = None
                    
            if failsafe_element_found:
                value = dummy_value
            else:
                return failsafe_div(label, subform_name, value)
        elements = generate_static_subform_elements(element_config, form_name, value)

    subform_block = html.Div(
        [
            html.Label(label+' '),
            *elements,
        ], style={'backgroundColor': 'lightblue', 'padding': '10px'}
    )
    return subform_block

def generate_static_subform_elements(element_config, form_name, value=None):
    label = element_config.get("label", element_config["element_id"])
    subform_name = form_name+'-'+element_config["element_id"]

    subform_ls = [dict(id=id, **val) for id, val in element_config['parameters'].items()]

    elements = []
    used_subform_idxs = []
    for key, subform_value in value.items():
        subform = None
        for sf in subform_ls:
            if key == str(sf['id']):
                used_subform_idxs.append(sf['id'])
                subform = sf
                break
        sf_elements = []
        if subform is None:
            sf_elements.append(failsafe_div(key, subform_name, json.dumps(subform_value, indent=2)))
            subform_label = 'failsafe:'+key
        else:
            subform_label = subform.get('label', None)
            for field, config in subform.items():
                if type(config) is not dict:
                    continue
                sf_elements.append(component_for_element(
                    element_config=dict(element_id=f'{key}|{field}', **config),
                    form_name=subform_name,
                    value=subform_value.get(field, None)
                ))
        elements.append(html.Div(
            ([html.B(subform_label)] if subform_label is not None else []) +
            [
                *sf_elements
            ], style={'border': '1px solid black', 'padding': '10px'}
        ))

    return elements

def generate_dynamic_subform_elements(element_config, form_name, value=None):
    label = element_config.get("label", element_config["element_id"])
    subform_name = form_name+'-'+element_config["element_id"]

    subform_names = get_dropdown_options(
        element_config["parameters"]["source_table"],
        element_config["parameters"]["value_column"],
        element_config["parameters"]["label_column"],
    )
    subform_key_values = get_dropdown_options(
        element_config["parameters"]["source_table"],
        element_config["parameters"]["value_column"],
        'key_values',
    )

    if subform_names is None or subform_key_values is None:
        return html.Div([html.Label(f"No subforms found for {element_config['label']}"),])

    subform_ls = []
    for id in set([d['value'] for l in [subform_key_values, subform_names] for d in l ]):
        subform = {}
        subform['id'] = id
        subform_label = [d['label'] for d in subform_names if d['value'] == id]
        if len(subform_label) != 1:
            print(f"Error in subform, no label for subform id {id}")
        subform['label'] = subform_label[0]
        key_values = [d['label'] for d in subform_key_values if d['value'] == id]
        if len(key_values) != 1:
            print(f"Error in subform, no key_values for subform id {id}")
        subform['key_values'] = json.loads(key_values[0])
        subform_ls.append(subform)


    elements = []
    used_subform_idxs = []
    for key, subform_value in value.items():
        subform = None
        for sf in subform_ls:
            if key == str(sf['id']):
                used_subform_idxs.append(sf['id'])
                subform = sf
                break
        sf_elements = []
        if subform is None:
            sf_elements.append(failsafe_div(key, subform_name, json.dumps(subform_value, indent=2)))
            subform_label = 'failsafe:'+key
        else:
            subform_label = subform['label']
            for field, config in subform['key_values'].items():
                sf_elements.append(component_for_element(
                    element_config=dict(element_id=f'{key}|{field}', **config),
                    form_name=subform_name,
                    value=subform_value[field]
                ))
        elements.append(html.Div(
            [
                html.B(subform_label),
                *sf_elements
            ], style={'border': '1px solid black', 'padding': '10px'}
        ))
    
    available_subforms = [subform for subform in subform_names if subform['value'] not in used_subform_idxs]

    elements += [
        dcc.Dropdown(
            id={"type": "input", "form": subform_name, "element": 'subform_selector'},
            options=available_subforms,
            placeholder='Add new...',
            clearable=True,
        ),
    ]
    return elements



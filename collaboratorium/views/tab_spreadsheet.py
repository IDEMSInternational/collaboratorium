"""
tab_spreadsheet.py
CPU-bound layout generation for AG Grid components.
Translates raw graph elements into interactive, paginated spreadsheets.
"""
import pandas as pd
from dash import html, Input, Output
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from db import get_dropdown_options, get_relation_links
from report_generator import format_subform_data

def _resolve_foreign_keys(data, table_name, config, dropdown_cache):
    table_fks = {
        child_col: (parent_table, parent_col) 
        for (child_tbl, child_col), (parent_table, parent_col) in config.fk_map.items() 
        if child_tbl == table_name
    }
    
    if not table_fks:
        return data
        
    fk_lookups = {}
    for col, (parent_table, parent_col) in table_fks.items():
        label_col = "name"
        form_name = config.get("default_forms", {}).get(table_name)
        if form_name:
            elem_cfg = config.get("forms", {}).get(form_name, {}).get("elements", {}).get(col, {})
            label_col = elem_cfg.get("parameters", {}).get("label_column", "name")
            
        cache_key = (parent_table, parent_col, label_col)
        if cache_key not in dropdown_cache:
            options = get_dropdown_options(parent_table, parent_col, label_col)
            dropdown_cache[cache_key] = {str(opt['value']): opt['label'] for opt in (options or [])}
        
        fk_lookups[col] = dropdown_cache[cache_key]

    for row in data:
        for col, lookup in fk_lookups.items():
            val = row.get(col)
            if val is None or val == "" or (isinstance(val, float) and pd.isna(val)):
                row[col] = ""  
            else:
                str_val = str(val).split('.')[0] if str(val).endswith('.0') else str(val)
                if str_val in lookup:
                    row[col] = lookup[str_val] if lookup[str_val] else f"Unnamed ({str_val})"
                else:
                    row[col] = ""
                    
    return data


def register_spreadsheet_callbacks(app, config):
    @app.callback(
        Output('spreadsheet-tabs', 'children'),
        Output('spreadsheet-tabs', 'active_tab'),
        Output('spreadsheet-grid-container', 'children'),
        Input('intermediate-graph-data', 'data'),
        Input('spreadsheet-tabs', 'active_tab') # Making this an input guarantees grid updates on click
    )
    def render_spreadsheet(elements, active_tab):
        if not elements:
            return [], None, None

        nodes = [e['data'] for e in elements if 'source' not in e['data']]
        if not nodes:
            return [], None, None

        nodes_by_type = {}
        for n in nodes:
            t = n.get('type')
            if t not in nodes_by_type:
                nodes_by_type[t] = []
            row = {'id': n['id']}
            row.update(n.get('properties', {}))
            nodes_by_type[t].append(row)

        # 1. Build Tab Navigation (No Empty Tabs)
        available_tables = [t for t in config.get("node_tables", []) if t in nodes_by_type]
        tabs = [
            dbc.Tab(label=t.replace('_', ' ').title(), tab_id=f"subtab-{t}")
            for t in available_tables
        ]
        
        if not tabs:
            return [], None, None

        # 2. Determine Active Tab
        valid_tab_ids = [f"subtab-{t}" for t in available_tables]
        if active_tab not in valid_tab_ids:
            active_tab = valid_tab_ids[0]

        # 3. Build Only the Active Grid
        active_table = active_tab.replace("subtab-", "")
        data = nodes_by_type[active_table]
        dropdown_cache = {}
        
        data = _resolve_foreign_keys(data, active_table, config, dropdown_cache)
        df = pd.DataFrame(data)

        if active_table == 'activities' and not df.empty:                        
            people_opts = get_dropdown_options('people', 'id', 'name')
            people_map = {row['value']: row['label'] for row in people_opts} if people_opts else {}
            
            init_opts = get_dropdown_options('initiatives', 'id', 'name')
            init_map = {row['value']: row['label'] for row in init_opts} if init_opts else {}
            
            activity_ids = df['id'].apply(lambda x: int(str(x).split('-')[-1])).tolist()
            
            p_links = get_relation_links('activity_people_links', 'activity_id', 'person_id', activity_ids)
            i_links = get_relation_links('activity_initiative_links', 'activity_id', 'initiative_id', activity_ids)
            
            p_links_map = p_links.groupby('activity_id')['person_id'].apply(list).to_dict()
            i_links_map = i_links.groupby('activity_id')['initiative_id'].apply(list).to_dict()
            
            df['linked_people'] = df.apply(lambda r: ", ".join([people_map[pid] for pid in p_links_map.get(int(str(r['id']).split('-')[-1]), []) if pid in people_map]) or "None", axis=1)
            df['linked_initiatives'] = df.apply(lambda r: ", ".join([init_map.get(iid, f"Initiative {iid}") for iid in i_links_map.get(int(str(r['id']).split('-')[-1]), []) if iid in init_map]) or "None", axis=1)
        
        if 'timestamp' in df.columns:
            df = df.sort_values('timestamp', ascending=False)

        if 'description' in df.columns:
            df['description'] = df['description'].apply(lambda x: format_subform_data(x) if pd.notna(x) else x)
        
        df['edit_action'] = df['id'].apply(lambda x: f"[✏️ Edit](#edit/{active_table}/{str(x).split('-')[-1]})")
        
        columns = [{"headerName": "Action", "field": "edit_action", "cellRenderer": "markdown", "width": 90, "pinned": "left"}]
        
        if 'timestamp' in df.columns:
            columns.append({
                "headerName": "Updated",
                "field": "timestamp",
                "width": 120,
                "pinned": "left",
                "sortable": True,
                "valueFormatter": {
                    "function": (
                        "function(params) {"
                        "  if (!params.value) return '';"
                        "  var diff = (new Date() - new Date(params.value)) / 1000;"
                        "  if (isNaN(diff) || diff < 0) return '';"
                        "  if (diff < 3600) return Math.floor(diff/60) + 'm';"
                        "  if (diff < 86400) return Math.floor(diff/3600) + 'h';"
                        "  if (diff < 86400*7) return Math.floor(diff/86400) + 'd';"
                        "  return Math.floor(diff/(86400*7)) + 'w';"
                        "}"
                    )
                }
            })
            
        for col in df.columns:
            if col not in ['timestamp', 'version', 'created_by', 'edit_action', 'id', 'status']:
                col_cfg = {
                    "headerName": col.replace('_', ' ').title(), 
                    "field": col,
                    "filter": True
                }
                if col == 'description':
                    col_cfg["cellRenderer"] = "markdown"
                    col_cfg["autoHeight"] = True
                    
                columns.append(col_cfg)
                
        grid_component = dag.AgGrid(
            id=f"spreadsheet-table-{active_table}",
            rowData=df.to_dict('records'),
            columnDefs=columns,
            defaultColDef={"sortable": True, "filter": True, "resizable": True},
            dashGridOptions={
                "pagination": True,
                "paginationPageSize": 20,
                "suppressColumnVirtualisation": True,
                "enableCellTextSelection": True,
                "getRowId": "params.data.id" # Forcing native React updating based on data ID
            },
            className="ag-theme-alpine",
            style={"height": "600px", "width": "100%"}
        )
            
        return tabs, active_tab, grid_component
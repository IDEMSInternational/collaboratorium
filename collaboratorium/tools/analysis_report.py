import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import sqlite3
import os
import random
from datetime import datetime, timedelta

# ==========================================
# PART 1: CONFIGURATION
# ==========================================

ANALYTICS_DB = 'analytics.db'
MAIN_DB = 'database.db'
SHOW_REAL_NAMES = False 
EXCLUDED_USER_ID = 23

# ==========================================
# PART 2: DATA LOADING & PROCESSING
# ==========================================

def get_db_connection(db_file):
    if not os.path.exists(db_file):
        return None
    try:
        return sqlite3.connect(db_file)
    except Exception:
        return None

def load_data():
    conn_main = get_db_connection(MAIN_DB)
    conn_analytics = get_db_connection(ANALYTICS_DB)

    if not conn_main or not conn_analytics:
        print("Error: Database files not found.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    try:
        q_init = "SELECT id, 'initiatives' as type, responsible_person, created_by, version, CAST(timestamp AS TEXT) as timestamp FROM initiatives"
        q_cont = "SELECT id, 'contracts' as type, responsible_person, created_by, version, CAST(timestamp AS TEXT) as timestamp FROM contracts"
        q_act = "SELECT id, 'activities' as type, NULL as responsible_person, created_by, version, CAST(timestamp AS TEXT) as timestamp FROM activities"

        df_init = pd.read_sql(q_init, conn_main)
        df_cont = pd.read_sql(q_cont, conn_main)
        df_act = pd.read_sql(q_act, conn_main)
        
        df_people = pd.read_sql("SELECT id, name FROM people", conn_main)
        
        df_analytics_raw = pd.read_sql("SELECT id, person_id, requested_table, requested_id, CAST(timestamp AS TEXT) as timestamp FROM analytics", conn_analytics)
        
        # Load the new view_analytics table
        df_view_analytics = pd.DataFrame()
        try:
            df_view_analytics = pd.read_sql("SELECT * FROM view_analytics", conn_analytics)
            if not df_view_analytics.empty:
                df_view_analytics['timestamp'] = pd.to_datetime(df_view_analytics['timestamp'], format='ISO8601', errors='coerce')
        except Exception as e:
            print(f"Notice: view_analytics table missing or empty: {e}")

        if EXCLUDED_USER_ID is not None and not df_analytics_raw.empty:
            df_analytics_raw = df_analytics_raw[df_analytics_raw['person_id'] != EXCLUDED_USER_ID]

        if EXCLUDED_USER_ID is not None and not df_view_analytics.empty:
            df_view_analytics = df_view_analytics[df_view_analytics['person_id'] != EXCLUDED_USER_ID]

    except Exception as e:
        print(f"Error reading databases: {e}")
        conn_main.close()
        conn_analytics.close()
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    conn_main.close()
    conn_analytics.close()

    if not SHOW_REAL_NAMES:
        nums = list(range(1, len(df_people['name'])+1))
        random.shuffle(nums)
        df_people['name'] = [f"anon{n}" for n in nums]

    df_content_all = pd.concat([df_init, df_cont, df_act], ignore_index=True)
    df_content_all['timestamp'] = pd.to_datetime(df_content_all['timestamp'], format='ISO8601', errors='coerce')

    df_creations = df_content_all[df_content_all['version'] == 1].copy()
    df_edits = df_content_all[df_content_all['version'] > 1].copy()

    if df_analytics_raw.empty:
        df_analytics_enriched = pd.DataFrame()
    else:
        df_analytics_raw['timestamp'] = pd.to_datetime(df_analytics_raw['timestamp'], format='ISO8601', errors='coerce')
        df_analytics_enriched = df_analytics_raw.merge(
            df_people[['id', 'name']], 
            left_on='person_id', 
            right_on='id', 
            how='left'
        )
        df_analytics_enriched.rename(columns={'name': 'user_name'}, inplace=True)
        df_analytics_enriched['user_name'].fillna('Unknown', inplace=True)

        df_latest_content = df_content_all.sort_values('version').drop_duplicates(['id', 'type'], keep='last')

        def determine_type(row):
            item = df_latest_content[
                (df_latest_content['id'] == row['requested_id']) & 
                (df_latest_content['type'] == row['requested_table'])
            ]
            
            if item.empty:
                return "Unknown Content"

            viewer = row['person_id']
            creator = item.iloc[0]['created_by']
            owner = item.iloc[0]['responsible_person']

            if (viewer == creator) or (viewer == owner):
                return "Self (Own Work)"
            
            return "Collaboration"

        df_analytics_enriched['interaction_type'] = df_analytics_enriched.apply(determine_type, axis=1)

    return df_analytics_enriched, df_creations, df_edits, df_view_analytics

# ==========================================
# PART 3: DASH APP
# ==========================================

def init_analytics_app(server):
    """Initializes the analytics Dash app on the shared Flask server."""
    app = dash.Dash(__name__, server=server, url_base_pathname='/analytics/', external_stylesheets=[dbc.themes.BOOTSTRAP])
    app.title = "Collaboratorium Analytics"

    df_analytics_init, df_creations_init, _, _ = load_data()
    if not df_analytics_init.empty:
        min_date = min(df_analytics_init['timestamp'].min(), df_creations_init['timestamp'].min())
        max_date = datetime.now()
    else:
        min_date = datetime.now() - timedelta(days=30)
        max_date = datetime.now()

    app.layout = dbc.Container([
        html.H1("Collaboratorium Usage Analytics", className='text-center my-4', style={'color': 'var(--idems-text)'}),
        
        html.Div([
            html.Label("Filter Time Period:", className="me-2"),
            dcc.DatePickerRange(
                id='date-picker-range',
                start_date=min_date,
                end_date=max_date,
                display_format='YYYY-MM-DD'
            )
        ], className='text-center mb-4'),

        # Metrics Row
        html.Div([
            html.Div([
                html.H4(id='metric-views', style={'margin': '0', 'color': 'var(--idems-orange)', 'fontWeight': 'bold'}), 
                html.Span("Total Views", style={'color': 'var(--idems-text-muted)', 'fontWeight': '600', 'textTransform': 'uppercase', 'fontSize': '0.85rem'})
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '12px', 'backgroundColor': 'var(--idems-panel)', 'padding': '12px 24px', 'borderRadius': '50px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.05)', 'border': '1px solid var(--border-color)'}),
            
            html.Div([
                html.H4(id='metric-creations', style={'margin': '0', 'color': 'var(--idems-orange)', 'fontWeight': 'bold'}), 
                html.Span("New Items", style={'color': 'var(--idems-text-muted)', 'fontWeight': '600', 'textTransform': 'uppercase', 'fontSize': '0.85rem'})
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '12px', 'backgroundColor': 'var(--idems-panel)', 'padding': '12px 24px', 'borderRadius': '50px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.05)', 'border': '1px solid var(--border-color)'}),

            html.Div([
                html.H4(id='metric-edits', style={'margin': '0', 'color': 'var(--idems-orange)', 'fontWeight': 'bold'}), 
                html.Span("Edits", style={'color': 'var(--idems-text-muted)', 'fontWeight': '600', 'textTransform': 'uppercase', 'fontSize': '0.85rem'})
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '12px', 'backgroundColor': 'var(--idems-panel)', 'padding': '12px 24px', 'borderRadius': '50px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.05)', 'border': '1px solid var(--border-color)'}),
            
            html.Div([
                html.H4(id='metric-users', style={'margin': '0', 'color': 'var(--idems-orange)', 'fontWeight': 'bold'}), 
                html.Span("Active Users", style={'color': 'var(--idems-text-muted)', 'fontWeight': '600', 'textTransform': 'uppercase', 'fontSize': '0.85rem'})
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '12px', 'backgroundColor': 'var(--idems-panel)', 'padding': '12px 24px', 'borderRadius': '50px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.05)', 'border': '1px solid var(--border-color)'}),
            
            html.Div([
                html.H4(id='metric-advanced-views', style={'margin': '0', 'color': 'var(--idems-orange)', 'fontWeight': 'bold'}), 
                html.Span("Custom Pipelines", style={'color': 'var(--idems-text-muted)', 'fontWeight': '600', 'textTransform': 'uppercase', 'fontSize': '0.85rem'})
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '12px', 'backgroundColor': 'var(--idems-panel)', 'padding': '12px 24px', 'borderRadius': '50px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.05)', 'border': '1px solid var(--border-color)'}),

        ], style={'display': 'flex', 'flexDirection': 'row', 'flexWrap': 'wrap', 'justifyContent': 'center', 'gap': '15px', 'marginBottom': '30px'}),

        dbc.Row([
            dbc.Col([
                html.H5("Activity Timeline", className='text-center'),
                dcc.Graph(id='timeline-graph')
            ])
        ], className='mb-4'),

        dbc.Row([
            dbc.Col([
                html.H5("Work Styles (Self vs Collaboration)"), 
                dcc.Graph(id='collab-graph')
            ], md=6),
            dbc.Col([
                html.H5("User Activity Volume"), 
                dcc.Graph(id='volume-graph')
            ], md=6),
        ], className='mb-4'),

        dbc.Row([
            dbc.Col([
                html.H5("Content Popularity"), 
                dcc.Graph(id='pie-graph')
            ], md=6),
            dbc.Col([
                html.H5("Graph View Popularity"), 
                dcc.Graph(id='view-popularity-graph')
            ], md=6),
        ], className='mb-4'),

        html.Hr(className="my-5"),
        html.H3("Deep UX Metrics (Graph Builder)", className="text-center mb-4", style={'color': 'var(--idems-text-muted)'}),

        dbc.Row([
            dbc.Col([
                html.H6("Traversal Direction Bias", className='text-center'),
                dcc.Graph(id='direction-graph')
            ], md=4),
            dbc.Col([
                html.H6("Degrees of Separation", className='text-center'),
                dcc.Graph(id='degree-graph')
            ], md=4),
            dbc.Col([
                html.H6("Node Count (Render Stress)", className='text-center'),
                dcc.Graph(id='node-count-graph')
            ], md=4),
        ], className='mb-4'),

        dbc.Row([
            dbc.Col([
                html.H6("Visible Node Types (Frequency)"),
                dcc.Graph(id='node-types-graph')
            ])
        ], className='mb-5')

    ], fluid=True, style={'maxWidth': '1300px', 'padding': '20px'})

    @app.callback(
        [Output('timeline-graph', 'figure'),
         Output('collab-graph', 'figure'),
         Output('volume-graph', 'figure'),
         Output('pie-graph', 'figure'),
         Output('view-popularity-graph', 'figure'),
         Output('direction-graph', 'figure'),
         Output('degree-graph', 'figure'),
         Output('node-count-graph', 'figure'),
         Output('node-types-graph', 'figure'),
         Output('metric-views', 'children'),
         Output('metric-creations', 'children'),
         Output('metric-edits', 'children'),
         Output('metric-users', 'children'),
         Output('metric-advanced-views', 'children')],
        [Input('date-picker-range', 'start_date'),
         Input('date-picker-range', 'end_date')]
    )
    def update_dashboard(start_date, end_date):
        df_analytics, df_creations, df_edits, df_views = load_data()

        empty_fig = go.Figure()

        if df_analytics.empty and df_creations.empty and df_views.empty:
            return (empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, 
                    empty_fig, empty_fig, empty_fig, empty_fig, 
                    "0", "0", "0", "0", "0")

        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)

        # Main Entity Analytics Filtering
        sub_analytics = df_analytics[(df_analytics['timestamp'] >= start) & (df_analytics['timestamp'] <= end)] if not df_analytics.empty else pd.DataFrame()
        sub_creations = df_creations[(df_creations['timestamp'] >= start) & (df_creations['timestamp'] <= end)] if not df_creations.empty else pd.DataFrame()
        sub_edits = df_edits[(df_edits['timestamp'] >= start) & (df_edits['timestamp'] <= end)] if not df_edits.empty else pd.DataFrame()
        sub_views = df_views[(df_views['timestamp'] >= start) & (df_views['timestamp'] <= end)] if not df_views.empty else pd.DataFrame()

        # Core Metrics
        count_views = len(sub_analytics)
        count_creations = len(sub_creations)
        count_edits = len(sub_edits)
        count_users = sub_analytics['person_id'].nunique() if not sub_analytics.empty else 0
        count_advanced = sub_views['used_advanced_pipeline'].sum() if not sub_views.empty and 'used_advanced_pipeline' in sub_views.columns else 0

        # Anonymization 
        if not SHOW_REAL_NAMES and not sub_analytics.empty:
            uids = sub_analytics.groupby(['person_id']).size().reset_index(name='count').sort_values('count', ascending=False)['person_id']
            new_names = {name: f"anon {i+1}" for i, name in enumerate(uids)}
            sub_analytics['user_name'] = sub_analytics['person_id'].map(new_names)
            sub_analytics.sort_values(by='user_name', inplace=True)

        # 1. Timeline
        dfs_to_concat = []
        if not sub_analytics.empty:
            tl_views = sub_analytics.set_index('timestamp').resample('D').size().reset_index(name='Count')
            tl_views['Category'] = 'Views'
            dfs_to_concat.append(tl_views)
        if not sub_creations.empty:
            tl_creates = sub_creations.set_index('timestamp').resample('D').size().reset_index(name='Count')
            tl_creates['Category'] = 'Creations'
            dfs_to_concat.append(tl_creates)
        if not sub_edits.empty:
            tl_edits = sub_edits.set_index('timestamp').resample('D').size().reset_index(name='Count')
            tl_edits['Category'] = 'Edits'
            dfs_to_concat.append(tl_edits)
            
        if dfs_to_concat:
            df_timeline = pd.concat(dfs_to_concat)
            fig_timeline = px.line(df_timeline, x='timestamp', y='Count', color='Category',
                                   color_discrete_map={'Views': '#3498db', 'Creations': '#2ecc71', 'Edits': '#f39c12'}, template='plotly_white')
            fig_timeline.update_layout(margin=dict(l=20, r=20, t=10, b=20))
        else:
            fig_timeline = empty_fig

        # 2. Collab, Volume & Pie
        if not sub_analytics.empty:
            df_stack = sub_analytics.groupby(['user_name', 'interaction_type']).size().reset_index(name='count')
            fig_collab = px.bar(df_stack, x='user_name', y='count', color='interaction_type',
                                color_discrete_map={'Self (Own Work)': '#95a5a6', 'Collaboration': '#9b59b6'},
                                template='plotly_white')
            fig_collab.update_layout(xaxis_title=None, yaxis_title="Interactions", legend_title=None)
            
            df_vol = sub_analytics['user_name'].value_counts().reset_index()
            df_vol.columns = ['user_name', 'count']
            fig_vol = px.bar(df_vol, x='user_name', y='count', template='plotly_white', color_discrete_sequence=['var(--idems-orange)'])
            fig_vol.update_layout(xaxis_title=None, yaxis_title="Total Activity")
            
            df_pie = sub_analytics['requested_table'].value_counts().reset_index()
            df_pie.columns = ['Type', 'count']
            fig_pie = px.pie(df_pie, values='count', names='Type', hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
        else:
            fig_collab = fig_vol = fig_pie = empty_fig

        # ----------------------------------------------------------------------
        # NEW UX ANALYTICS GRAPHS
        # ----------------------------------------------------------------------
        fig_views = fig_dir = fig_deg = fig_node_count = fig_types = empty_fig

        if not sub_views.empty:
            # 1. View Popularity
            if 'view_id' in sub_views.columns:
                df_view_counts = sub_views['view_id'].value_counts().reset_index()
                df_view_counts.columns = ['View', 'Count']
                fig_views = px.bar(df_view_counts, x='View', y='Count', template='plotly_white', 
                                   color_discrete_sequence=['#9b51e0'])
                fig_views.update_layout(xaxis_title=None, yaxis_title="Times Used")

            # 2. Traversal Direction Bias
            if 'degree_inout' in sub_views.columns:
                # Handle possible multiple/comma-sep if users check multiple boxes
                dir_series = sub_views['degree_inout'].dropna().str.split(',').explode().str.strip()
                df_dir = dir_series.value_counts().reset_index()
                df_dir.columns = ['Direction', 'Count']
                if not df_dir.empty:
                    fig_dir = px.pie(df_dir, values='Count', names='Direction', hole=0.4, 
                                     color_discrete_sequence=px.colors.sequential.Teal)
                    fig_dir.update_layout(margin=dict(t=10, b=10))

            # 3. Degrees of Separation (Bar chart acting as Histogram to fix discrete values)
            if 'degree' in sub_views.columns:
                df_deg = sub_views['degree'].dropna().value_counts().reset_index()
                df_deg.columns = ['Degree', 'Count']
                df_deg = df_deg.sort_values(by='Degree')
                if not df_deg.empty:
                    fig_deg = px.bar(df_deg, x='Degree', y='Count', template='plotly_white', 
                                     color_discrete_sequence=['#f28b20'])
                    # Force x-axis to be categorical so integer ticks don't interpolate weirdly
                    fig_deg.update_xaxes(type='category')
                    fig_deg.update_layout(margin=dict(t=10, b=10))

            # 4. Node Count Stress
            if 'node_count' in sub_views.columns:
                df_nodes = sub_views['node_count'].dropna()
                if not df_nodes.empty:
                    fig_node_count = px.histogram(sub_views, x='node_count', nbins=20, template='plotly_white', 
                                                  color_discrete_sequence=['#dc3545'])
                    fig_node_count.update_layout(xaxis_title="Nodes Rendered", yaxis_title="Frequency", margin=dict(t=10, b=10))

            # 5. Visible Node Types
            if 'node_types' in sub_views.columns:
                types_series = sub_views['node_types'].dropna().str.split(',').explode().str.strip()
                df_types = types_series.value_counts().reset_index()
                df_types.columns = ['Node Type', 'Frequency']
                if not df_types.empty:
                    fig_types = px.bar(df_types, x='Node Type', y='Frequency', template='plotly_white', 
                                       color_discrete_sequence=['#649ba3'])
                    fig_types.update_layout(xaxis_title=None, yaxis_title="Times Included")

        return (fig_timeline, fig_collab, fig_vol, fig_pie, fig_views, 
                fig_dir, fig_deg, fig_node_count, fig_types,
                f"{count_views:,}", f"{count_creations:,}", f"{count_edits:,}", 
                f"{count_users:,}", f"{int(count_advanced):,}")

    return app

if __name__ == '__main__':
    from flask import Flask
    app_server = Flask(__name__)
    analytics_app = init_analytics_app(app_server)
    analytics_app.run_server(debug=True, port=8051)
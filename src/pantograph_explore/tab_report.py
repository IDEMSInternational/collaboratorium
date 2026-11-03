"""
tab_report.py
Renders formatted hierarchical Markdown reports based on the stable data cache.

The report is rendered twice from one set of lookups: once with the actions its
config defines — the edit link, and the add links that let someone record
missing work from the report they noticed it was missing in — and once without
them. The first is what the page shows; the second is what the copy button
carries, because an app's own affordances have no business in the document
somebody pastes into a final report. Copying used to hand over whatever was on
screen, edit links included.
"""
from dash import html, dcc, Input, Output
import dash_bootstrap_components as dbc
from pantograph.report_generator import generate_markdown_report, report_context

def register_report_callbacks(app, config):
    @app.callback(
        Output('report-container', 'children'),
        Output('report-clipboard', 'content'),
        Output('report-title', 'children'),
        Input('intermediate-graph-data', 'data'),
        Input('report-show-actions', 'value'),
    )
    def render_report(elements, show_actions):
        if not elements:
            return html.Div("No data to display.", className="text-muted p-4 text-center"), "", ""

        try:
            reports_cfg = config.get("reports", {})
            if not reports_cfg:
                return (
                    html.Div("No reports configured under 'reports:'.", className="text-muted p-4 text-center"),
                    "", "",
                )

            report_id = list(reports_cfg.keys())[0]
            report_cfg = reports_cfg[report_id]

            # One context, two renders: the names and provenance behind the two
            # versions are the same rows, so the copy cannot disagree with what
            # is on screen, and the second render costs no further queries.
            context = report_context()
            shown_md = generate_markdown_report(
                report_cfg, elements, include_actions=bool(show_actions), context=context,
            )
            clean_md = (
                shown_md if not show_actions
                else generate_markdown_report(
                    report_cfg, elements, include_actions=False, context=context,
                )
            )

            return (
                html.Div(
                    dcc.Markdown(shown_md, dangerously_allow_html=True),
                    style={'backgroundColor': 'white', 'padding': '30px', 'borderRadius': '8px', 'border': '1px solid var(--border-color)', 'minHeight': '400px'}
                ),
                clean_md,
                report_cfg.get('name', 'Report'),
            )

        except Exception as e:
            return html.Div(f"Error generating report: {e}", className="text-danger p-4"), "", ""

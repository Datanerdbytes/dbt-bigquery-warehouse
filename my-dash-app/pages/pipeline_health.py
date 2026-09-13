import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import plotly.express as px
import pandas as pd
from data_loader import load_pipeline_health_summary, load_dbt_execution_logs

dash.register_page(__name__, path="/pipeline-health", name="Pipeline Health")

def layout():
    # Load metadata
    df_summary = load_pipeline_health_summary()
    df_logs = load_dbt_execution_logs()

    # Fallback default values
    status = df_summary["overall_system_status"].iloc[0] if not df_summary.empty else "UNKNOWN"
    passed = df_summary["passed_tests"].iloc[0] if not df_summary.empty else 0
    failed = df_summary["failed_tests"].iloc[0] if not df_summary.empty else 0
    warnings = df_summary["warning_tests"].iloc[0] if not df_summary.empty else 0
    avg_dur = df_summary["avg_model_duration_sec"].iloc[0] if not df_summary.empty else 0.0

    # Badge styling
    status_color = "success" if status == "HEALTHY" else ("warning" if status == "WARNING" else "danger")

    # Table columns for dash.AgGrid
    column_defs = [
        {"field": "run_timestamp", "headerName": "Timestamp", "sort": "desc", "width": 180},
        {"field": "resource_type", "headerName": "Type", "width": 110},
        {"field": "node_name", "headerName": "Node / Test Name", "flex": 1, "filter": True},
        {"field": "target_table", "headerName": "Target Table", "width": 160, "filter": True},
        {"field": "status", "headerName": "Status", "width": 120, 
         "cellStyle": {
             "styleConditions": [
                 {"condition": "params.value == 'pass' || params.value == 'success'", "style": {"color": "#2ea043", "fontWeight": "bold"}},
                 {"condition": "params.value == 'fail' || params.value == 'error'", "style": {"color": "#da3633", "fontWeight": "bold"}},
                 {"condition": "params.value == 'warn'", "style": {"color": "#d29922", "fontWeight": "bold"}}
             ]
         }},
        {"field": "execution_time_seconds", "headerName": "Duration (s)", "width": 130},
        {"field": "rows_affected", "headerName": "Failed Rows", "width": 130},
        {"field": "error_message", "headerName": "Error Details", "flex": 1.5, "tooltipField": "error_message"}
    ]

    return html.Div(
        [
            # Page Title & System Status Badge
            html.Div(
                [
                    html.H3("Data Pipeline Health & Observability", className="text-white fw-bold mb-1"),
                    html.P("Real-time monitoring for BigQuery ingestion pipelines and dbt assertions.", className="text-muted small mb-0"),
                ],
                className="mb-4"
            ),

            # KPI Bar
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("System Status", className="text-muted small fw-bold d-block mb-1"),
                                dbc.Badge(status, color=status_color, className="fs-6 px-3 py-2")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center"
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Passed Tests", className="text-muted small fw-bold d-block mb-1"),
                                html.H4(f"{passed:,}", className="text-success fw-bold mb-0")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center"
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Failed / Errors", className="text-muted small fw-bold d-block mb-1"),
                                html.H4(f"{failed:,}", className="text-danger fw-bold mb-0")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center"
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Avg Test Duration", className="text-muted small fw-bold d-block mb-1"),
                                html.H4(f"{avg_dur:.2f}s", className="text-white fw-bold mb-0")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center"
                        ),
                        width=12, md=3
                    ),
                ],
                className="g-3 mb-4"
            ),

            # AgGrid Detailed Execution Logs
            html.Div(
                [
                    html.H5("Execution & Test History", className="text-white fw-bold mb-3"),
                    dag.AgGrid(
                        id="pipeline-execution-grid",
                        rowData=df_logs.to_dict("records"),
                        columnDefs=column_defs,
                        defaultColDef={"resizable": True, "sortable": True, "filter": True},
                        dashGridOptions={"pagination": True, "paginationPageSize": 15},
                        className="ag-theme-alpine-dark",
                        style={"height": "500px", "width": "100%"}
                    )
                ],
                className="dark-card p-4 rounded shadow-sm"
            )
        ]
    )
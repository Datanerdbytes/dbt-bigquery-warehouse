import dash
from dash import html, dcc, callback, Input, Output, dash_table
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import plotly.express as px
import pandas as pd
from data_loader import load_pipeline_health_summary, load_dbt_execution_logs, load_model_coverage_details, load_column_coverage_details

dash.register_page(__name__, path="/pipeline-health", name="Pipeline Health")


def layout():
    # Load metadata
    df_summary = load_pipeline_health_summary()
    df_logs = load_dbt_execution_logs()
    df_model_coverage = load_model_coverage_details()
    df_column_coverage = load_column_coverage_details()

    # Fallback default values
    status = df_summary["overall_system_status"].iloc[0] if not df_summary.empty else "UNKNOWN"
    passed = df_summary["passed_tests"].iloc[0] if not df_summary.empty else 0
    failed = df_summary["failed_tests"].iloc[0] if not df_summary.empty else 0
    warnings = df_summary["warning_tests"].iloc[0] if not df_summary.empty else 0
    avg_dur = df_summary["avg_model_duration_sec"].iloc[0] if not df_summary.empty else 0.0

    # Coverage metrics
    coverage_pct = df_summary["overall_column_coverage_pct"].iloc[0] if not df_summary.empty else 0.0
    total_models = df_summary["total_models"].iloc[0] if not df_summary.empty else 0
    total_columns = df_summary["total_columns"].iloc[0] if not df_summary.empty else 0
    total_tested = df_summary["total_columns_with_tests"].iloc[0] if not df_summary.empty else 0
    total_tests = df_summary["total_tests"].iloc[0] if not df_summary.empty else 0
    models_fully = df_summary["models_fully_covered"].iloc[0] if not df_summary.empty else 0
    models_well = df_summary["models_well_covered"].iloc[0] if not df_summary.empty else 0
    models_poor = df_summary["models_poorly_covered"].iloc[0] if not df_summary.empty else 0
    last_run = df_summary["last_dbt_run"].iloc[0] if not df_summary.empty else None

    # Badge styling
    status_color = "success" if status == "HEALTHY" else ("warning" if status == "WARNING" else "danger")
    coverage_color = "success" if coverage_pct >= 90 else ("warning" if coverage_pct >= 70 else "danger")

    # Table columns for dash.AgGrid - Execution logs
    exec_column_defs = [
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

    # Model coverage table
    model_cov_column_defs = [
        {"field": "model_name", "headerName": "Model", "width": 200, "filter": True, "sort": True},
        {"field": "schema", "headerName": "Schema", "width": 100, "filter": True},
        {"field": "total_columns", "headerName": "Total Cols", "width": 100},
        {"field": "columns_with_tests", "headerName": "Tested Cols", "width": 110},
        {"field": "column_coverage_pct", "headerName": "Coverage %", "width": 120,
         "cellRenderer": "agAnimateShowChangeCellRenderer",
         "cellStyle": {
             "styleConditions": [
                 {"condition": "params.value == 100", "style": {"color": "#2ea043", "fontWeight": "bold"}},
                 {"condition": "params.value >= 80", "style": {"color": "#d29922", "fontWeight": "bold"}},
                 {"condition": "params.value < 50", "style": {"color": "#da3633", "fontWeight": "bold"}}
             ]
         }},
        {"field": "total_tests", "headerName": "Total Tests", "width": 110},
    ]

    # Column coverage table (for drill-down)
    col_cov_column_defs = [
        {"field": "model_name", "headerName": "Model", "width": 180, "filter": True},
        {"field": "schema", "headerName": "Schema", "width": 90, "filter": True},
        {"field": "column_name", "headerName": "Column", "width": 180, "filter": True},
        {"field": "column_description", "headerName": "Description", "flex": 1, "filter": True},
        {"field": "data_type", "headerName": "Type", "width": 100},
        {"field": "test_count", "headerName": "# Tests", "width": 80},
        {"field": "test_names", "headerName": "Test Names", "flex": 1.5, "tooltipField": "test_names"},
        {"field": "has_tests", "headerName": "Tested", "width": 80,
         "cellRenderer": "agCheckboxCellRenderer",
         "cellStyle": {
             "styleConditions": [
                 {"condition": "params.value == true", "style": {"color": "#2ea043", "textAlign": "center"}},
                 {"condition": "params.value == false", "style": {"color": "#da3633", "textAlign": "center", "fontWeight": "bold"}}
             ]
         }},
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

            # KPI Bar - Row 1: System Status
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("System Status", className="text-muted small fw-bold d-block mb-1"),
                                dbc.Badge(status, color=status_color, className="fs-6 px-3 py-2")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center d-flex flex-column justify-content-center",
                            style={"minHeight": "120px"}
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Last dbt Run", className="text-muted small fw-bold d-block mb-1"),
                                html.H6(f"{pd.to_datetime(last_run).strftime('%Y-%m-%d %H:%M UTC') if last_run else 'N/A'}", className="text-white fw-bold mb-0 small")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center d-flex flex-column justify-content-center",
                            style={"minHeight": "120px"}
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Passed Tests", className="text-muted small fw-bold d-block mb-1"),
                                html.H4(f"{passed:,}", className="text-success fw-bold mb-0")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center d-flex flex-column justify-content-center",
                            style={"minHeight": "120px"}
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Failed / Errors", className="text-muted small fw-bold d-block mb-1"),
                                html.H4(f"{failed:,}", className="text-danger fw-bold mb-0")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center d-flex flex-column justify-content-center",
                            style={"minHeight": "120px"}
                        ),
                        width=12, md=3
                    ),
                ],
                className="g-3 mb-3"
            ),

            # KPI Bar - Row 2: Coverage Metrics
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Column Coverage", className="text-muted small fw-bold d-block mb-1"),
                                html.H4(f"{coverage_pct:.1f}%", className=f"text-{coverage_color} fw-bold mb-0")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center d-flex flex-column justify-content-center",
                            style={"minHeight": "120px"}
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Columns Tested", className="text-muted small fw-bold d-block mb-1"),
                                html.H4(f"{total_tested:,} / {total_columns:,}", className="text-white fw-bold mb-0")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center d-flex flex-column justify-content-center",
                            style={"minHeight": "120px"}
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Total Tests", className="text-muted small fw-bold d-block mb-1"),
                                html.H4(f"{total_tests:,}", className="text-info fw-bold mb-0")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center d-flex flex-column justify-content-center",
                            style={"minHeight": "120px"}
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Avg Test Duration", className="text-muted small fw-bold d-block mb-1"),
                                html.H4(f"{avg_dur:.2f}s", className="text-white fw-bold mb-0")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center d-flex flex-column justify-content-center",
                            style={"minHeight": "120px"}
                        ),
                        width=12, md=3
                    ),
                ],
                className="g-3 mb-3"
            ),

            # KPI Bar - Row 3: Model Coverage Summary
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Models (100%)", className="text-muted small fw-bold d-block mb-1"),
                                html.H4(f"{models_fully:,}", className="text-success fw-bold mb-0"),
                                html.Span(f"of {total_models}", className="text-muted small")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center d-flex flex-column justify-content-center",
                            style={"minHeight": "120px"}
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Models (≥80%)", className="text-muted small fw-bold d-block mb-1"),
                                html.H4(f"{models_well:,}", className="text-warning fw-bold mb-0"),
                                html.Span(f"of {total_models}", className="text-muted small")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center d-flex flex-column justify-content-center",
                            style={"minHeight": "120px"}
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Models (<50%)", className="text-muted small fw-bold d-block mb-1"),
                                html.H4(f"{models_poor:,}", className="text-danger fw-bold mb-0"),
                                html.Span(f"of {total_models}", className="text-muted small")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center d-flex flex-column justify-content-center",
                            style={"minHeight": "120px"}
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        html.Div(
                            [
                                html.Span("Warnings", className="text-muted small fw-bold d-block mb-1"),
                                html.H4(f"{warnings:,}", className="text-warning fw-bold mb-0")
                            ],
                            className="dark-card p-3 rounded shadow-sm text-center d-flex flex-column justify-content-center",
                            style={"minHeight": "120px"}
                        ),
                        width=12, md=3
                    ),
                ],
                className="g-3 mb-4"
            ),

            # Tabs for different views
            dbc.Tabs(
                [
                    dbc.Tab(
                        [
                            # AgGrid Detailed Execution Logs
                            html.Div(
                                [
                                    html.H5("Execution & Test History", className="text-white fw-bold mb-3"),
                                    dag.AgGrid(
                                        id="pipeline-execution-grid",
                                        rowData=df_logs.to_dict("records"),
                                        columnDefs=exec_column_defs,
                                        defaultColDef={"resizable": True, "sortable": True, "filter": True},
                                        dashGridOptions={"pagination": True, "paginationPageSize": 15},
                                        className="ag-theme-alpine-dark",
                                        style={"height": "500px", "width": "100%"}
                                    )
                                ],
                                className="dark-card p-4 rounded shadow-sm mt-3"
                            )
                        ],
                        label="Execution Logs",
                        tab_id="tab-execution"
                    ),
                    dbc.Tab(
                        [
                            # Model Coverage Grid
                            html.Div(
                                [
                                    html.H5("Model Test Coverage", className="text-white fw-bold mb-3"),
                                    dag.AgGrid(
                                        id="model-coverage-grid",
                                        rowData=df_model_coverage.to_dict("records"),
                                        columnDefs=model_cov_column_defs,
                                        defaultColDef={"resizable": True, "sortable": True, "filter": True},
                                        dashGridOptions={"pagination": True, "paginationPageSize": 20, "domLayout": "autoHeight"},
                                        className="ag-theme-alpine-dark",
                                        style={"height": "400px", "width": "100%"}
                                    )
                                ],
                                className="dark-card p-4 rounded shadow-sm mt-3"
                            )
                        ],
                        label="Model Coverage",
                        tab_id="tab-model-coverage"
                    ),
                    dbc.Tab(
                        [
                            # Column Coverage Grid (drill-down)
                            html.Div(
                                [
                                    html.H5("Column-Level Test Coverage", className="text-white fw-bold mb-3"),
                                    html.P("Columns without tests highlighted in red. Click column headers to sort/filter.", className="text-muted small mb-3"),
                                    dag.AgGrid(
                                        id="column-coverage-grid",
                                        rowData=df_column_coverage.to_dict("records"),
                                        columnDefs=col_cov_column_defs,
                                        defaultColDef={"resizable": True, "sortable": True, "filter": True},
                                        dashGridOptions={"pagination": True, "paginationPageSize": 25},
                                        className="ag-theme-alpine-dark",
                                        style={"height": "500px", "width": "100%"}
                                    )
                                ],
                                className="dark-card p-4 rounded shadow-sm mt-3"
                            )
                        ],
                        label="Column Coverage",
                        tab_id="tab-column-coverage"
                    ),
                ],
                id="pipeline-tabs",
                active_tab="tab-execution",
                className="mb-4"
            ),
        ]
    )
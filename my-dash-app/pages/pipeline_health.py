import dash
from dash import html, dcc, callback, Input, Output, dash_table
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import plotly.express as px
import pandas as pd
from data_loader import load_pipeline_health_summary, load_dbt_execution_logs, load_model_coverage_details, load_column_coverage_details, load_source_freshness

dash.register_page(__name__, path="/pipeline-health", name="Pipeline Health")


# Tooltip definitions for KPI cards
KPI_TOOLTIPS = {
    "source-freshness": "Time since the oldest bronze source table was loaded. Lower is fresher.",
    "latest-load": "Timestamp of the most recent bronze layer ingestion across all sources.",
    "passed-tests": "Number of dbt tests that passed in the latest execution run.",
    "failed-tests": "Number of dbt tests that failed (errors) in the latest execution run.",
    "column-coverage": "Percentage of model columns that have at least one test defined in the dbt manifest.",
    "columns-tested": "Number of columns with tests / total columns across all dbt models.",
    "total-tests": "Total count of all column-level tests defined across all models.",
    "avg-duration": "Average execution time per model/test in the latest dbt run.",
    "models-100": "Models where every column has at least one test (100% column coverage).",
    "models-80": "Models with 80% or higher column test coverage.",
    "models-50": "Models with less than 50% column test coverage (need attention).",
    "warnings": "Number of dbt tests that returned warnings (typically source-level tests).",
}


def create_kpi_card(title, value_id, value_children, subtitle=None, card_id=None, tooltip_key=None):
    """Create a KPI card with optional tooltip. Uses h-100 for consistent height across cards in a row."""
    card_content = html.Div(
        [
            html.Span(title, className="text-muted small fw-bold d-block mb-1"),
            html.Div(value_children, id=value_id, className="d-flex align-items-center justify-content-center flex-grow-1"),
            html.Small(subtitle, className="text-muted d-block mt-1") if subtitle else None,
        ],
        className="dark-card p-3 rounded shadow-sm text-center d-flex flex-column h-100",
        style={"minHeight": "120px"},
        id=card_id,
    )

    if tooltip_key and tooltip_key in KPI_TOOLTIPS:
        # Wrap in a div with h-100 and d-flex flex-column so the card fills the column height
        return html.Div(
            [
                card_content,
                dbc.Tooltip(KPI_TOOLTIPS[tooltip_key], target=card_id, placement="top", delay={"show": 200, "hide": 100}),
            ],
            className="h-100 d-flex flex-column",
            style={"minHeight": "120px"}
        )
    return card_content


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

    # Load source freshness
    df_source_freshness = load_source_freshness()

    # Badge styling
    status_color = "success" if status == "HEALTHY" else ("warning" if status == "WARNING" else "danger")
    coverage_color = "success" if coverage_pct >= 90 else ("warning" if coverage_pct >= 70 else "danger")

    # Source freshness color logic
    def get_freshness_color(hours):
        if hours <= 12:
            return "success"
        elif hours <= 24:
            return "warning"
        return "danger"

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

            # KPI Bar - Row 1: Source Freshness
            dbc.Row(
                [
                    dbc.Col(
                        create_kpi_card(
                            "Source Freshness",
                            "kpi-source-freshness",
                            html.Div([
                                html.H4(f"{df_source_freshness['hours_since_load'].min():.0f}h", className="text-white fw-bold mb-0"),
                                html.Small("oldest source", className="text-muted"),
                            ], className="d-flex flex-column align-items-center justify-content-center flex-grow-1 w-100") if not df_source_freshness.empty else html.H4("N/A", className="text-muted fw-bold mb-0"),
                            card_id="card-source-freshness",
                            tooltip_key="source-freshness",
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        create_kpi_card(
                            "Latest Load",
                            "kpi-latest-load",
                            html.H4(f"{pd.to_datetime(df_source_freshness['last_loaded'].max()).strftime('%Y-%m-%d %H:%M UTC') if not df_source_freshness.empty else 'N/A'}", className="text-white fw-bold mb-0"),
                            card_id="card-latest-load",
                            tooltip_key="latest-load",
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        create_kpi_card(
                            "Passed Tests",
                            "kpi-passed-tests",
                            html.H4(f"{passed:,}", className="text-success fw-bold mb-0"),
                            card_id="card-passed-tests",
                            tooltip_key="passed-tests",
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        create_kpi_card(
                            "Failed / Errors",
                            "kpi-failed-tests",
                            html.H4(f"{failed:,}", className="text-danger fw-bold mb-0"),
                            card_id="card-failed-tests",
                            tooltip_key="failed-tests",
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
                        create_kpi_card(
                            "Column Coverage",
                            "kpi-column-coverage",
                            html.H4(f"{coverage_pct:.1f}%", className=f"text-{coverage_color} fw-bold mb-0"),
                            card_id="card-column-coverage",
                            tooltip_key="column-coverage",
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        create_kpi_card(
                            "Columns Tested",
                            "kpi-columns-tested",
                            html.H4(f"{total_tested:,} / {total_columns:,}", className="text-white fw-bold mb-0"),
                            card_id="card-columns-tested",
                            tooltip_key="columns-tested",
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        create_kpi_card(
                            "Total Tests",
                            "kpi-total-tests",
                            html.H4(f"{total_tests:,}", className="text-info fw-bold mb-0"),
                            card_id="card-total-tests",
                            tooltip_key="total-tests",
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        create_kpi_card(
                            "Avg Test Duration",
                            "kpi-avg-duration",
                            html.H4(f"{avg_dur:.2f}s", className="text-white fw-bold mb-0"),
                            card_id="card-avg-duration",
                            tooltip_key="avg-duration",
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
                        create_kpi_card(
                            "Models (100%)",
                            "kpi-models-100",
                            [
                                html.H4(f"{models_fully:,}", className="text-success fw-bold mb-0"),
                                html.Span(f"of {total_models}", className="text-muted small"),
                            ],
                            card_id="card-models-100",
                            tooltip_key="models-100",
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        create_kpi_card(
                            "Models (≥80%)",
                            "kpi-models-80",
                            [
                                html.H4(f"{models_well:,}", className="text-warning fw-bold mb-0"),
                                html.Span(f"of {total_models}", className="text-muted small"),
                            ],
                            card_id="card-models-80",
                            tooltip_key="models-80",
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        create_kpi_card(
                            "Models (<50%)",
                            "kpi-models-50",
                            [
                                html.H4(f"{models_poor:,}", className="text-danger fw-bold mb-0"),
                                html.Span(f"of {total_models}", className="text-muted small"),
                            ],
                            card_id="card-models-50",
                            tooltip_key="models-50",
                        ),
                        width=12, md=3
                    ),
                    dbc.Col(
                        create_kpi_card(
                            "Warnings",
                            "kpi-warnings",
                            html.H4(f"{warnings:,}", className="text-warning fw-bold mb-0"),
                            card_id="card-warnings",
                            tooltip_key="warnings",
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
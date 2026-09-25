import dash
from dash import html, dcc, callback, Input, Output, dash_table
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from data_loader import (
    load_pipeline_health_summary, 
    load_dbt_execution_logs, 
    load_model_coverage_details, 
    load_column_coverage_details, 
    load_source_freshness,
    load_table_ingestion_logs,
    load_expensive_queries,
    load_bigquery_cost_metrics,
)

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
    # Column definitions for grids
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

    ingestion_column_defs = [
        {"field": "run_timestamp", "headerName": "Timestamp", "sort": "desc", "width": 180},
        {"field": "resource_type", "headerName": "Ingestion Type", "width": 160, "filter": True},
        {"field": "table_name", "headerName": "Source / Table Name", "width": 200, "filter": True},
        {"field": "target_table", "headerName": "Destination Table", "flex": 1, "filter": True},
        {"field": "rows_inserted", "headerName": "Rows Inserted", "width": 150, "type": "numericColumn",
         "cellStyle": {"fontWeight": "bold"}},
        {"field": "duration_seconds", "headerName": "Duration (s)", "width": 130},
        {"field": "status", "headerName": "Status", "width": 110,
         "cellStyle": {
             "styleConditions": [
                 {"condition": "params.value == 'pass' || params.value == 'success'", "style": {"color": "#2ea043", "fontWeight": "bold"}},
                 {"condition": "params.value == 'fail' || params.value == 'error'", "style": {"color": "#da3633", "fontWeight": "bold"}}
             ]
         }},
    ]

    bq_cost_column_defs = [
        {"field": "creation_time", "headerName": "Timestamp", "sort": "desc", "width": 180},
        {"field": "user_email", "headerName": "User / Service Account", "width": 220, "filter": True},
        {"field": "gb_processed", "headerName": "GB Processed", "width": 140, "type": "numericColumn"},
        {"field": "slot_seconds", "headerName": "Slot Seconds", "width": 130, "type": "numericColumn"},
        {"field": "duration_seconds", "headerName": "Duration (s)", "width": 120},
        {"field": "query", "headerName": "Query Text", "flex": 2, "filter": True},
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

            # KPI Cards Bar (populated via callback)
            dcc.Loading(
                id="pipeline-kpi-loading",
                type="circle",
                color="#10b981",
                children=[
                    dbc.Row(
                        [
                            dbc.Col(create_kpi_card("Source Freshness", "kpi-source-freshness-val", html.H4("...", className="text-muted fw-bold mb-0"), card_id="card-source-freshness", tooltip_key="source-freshness"), width=12, md=3),
                            dbc.Col(create_kpi_card("Latest Load", "kpi-latest-load-val", html.H4("...", className="text-muted fw-bold mb-0"), card_id="card-latest-load", tooltip_key="latest-load"), width=12, md=3),
                            dbc.Col(create_kpi_card("Passed Tests", "kpi-passed-tests-val", html.H4("...", className="text-success fw-bold mb-0"), card_id="card-passed-tests", tooltip_key="passed-tests"), width=12, md=3),
                            dbc.Col(create_kpi_card("Failed / Errors", "kpi-failed-tests-val", html.H4("...", className="text-danger fw-bold mb-0"), card_id="card-failed-tests", tooltip_key="failed-tests"), width=12, md=3),
                        ],
                        className="g-3 mb-3"
                    ),
                    dbc.Row(
                        [
                            dbc.Col(create_kpi_card("Column Coverage", "kpi-column-coverage-val", html.H4("...", className="text-white fw-bold mb-0"), card_id="card-column-coverage", tooltip_key="column-coverage"), width=12, md=3),
                            dbc.Col(create_kpi_card("Columns Tested", "kpi-columns-tested-val", html.H4("...", className="text-white fw-bold mb-0"), card_id="card-columns-tested", tooltip_key="columns-tested"), width=12, md=3),
                            dbc.Col(create_kpi_card("Total Tests", "kpi-total-tests-val", html.H4("...", className="text-info fw-bold mb-0"), card_id="card-total-tests", tooltip_key="total-tests"), width=12, md=3),
                            dbc.Col(create_kpi_card("Avg Test Duration", "kpi-avg-duration-val", html.H4("...", className="text-white fw-bold mb-0"), card_id="card-avg-duration", tooltip_key="avg-duration"), width=12, md=3),
                        ],
                        className="g-3 mb-3"
                    ),
                    dbc.Row(
                        [
                            dbc.Col(create_kpi_card("Models (100%)", "kpi-models-100-val", html.H4("...", className="text-success fw-bold mb-0"), card_id="card-models-100", tooltip_key="models-100"), width=12, md=3),
                            dbc.Col(create_kpi_card("Models (≥80%)", "kpi-models-80-val", html.H4("...", className="text-warning fw-bold mb-0"), card_id="card-models-80", tooltip_key="models-80"), width=12, md=3),
                            dbc.Col(create_kpi_card("Models (<50%)", "kpi-models-50-val", html.H4("...", className="text-danger fw-bold mb-0"), card_id="card-models-50", tooltip_key="models-50"), width=12, md=3),
                            dbc.Col(create_kpi_card("Warnings", "kpi-warnings-val", html.H4("...", className="text-warning fw-bold mb-0"), card_id="card-warnings", tooltip_key="warnings"), width=12, md=3),
                        ],
                        className="g-3 mb-4"
                    ),
                ],
                fullscreen=False,
                className="mb-3"
            ),

            # Main View Tabs
            dbc.Tabs(
                [
                    dbc.Tab(
                        [
                            html.Div(
                                [
                                    html.H5("Execution & Test History", className="text-white fw-bold mb-3"),
                                    dcc.Loading(
                                        id="pipeline-execution-loading",
                                        type="circle",
                                        color="#10b981",
                                        children=[
                                            dag.AgGrid(
                                                id="pipeline-execution-grid",
                                                rowData=[],
                                                columnDefs=exec_column_defs,
                                                defaultColDef={"resizable": True, "sortable": True, "filter": True},
                                                dashGridOptions={"pagination": True, "paginationPageSize": 15},
                                                className="ag-theme-alpine-dark",
                                                style={"height": "500px", "width": "100%"}
                                            )
                                        ]
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
                            html.Div(
                                [
                                    html.H5("Model Test Coverage", className="text-white fw-bold mb-3"),
                                    dcc.Loading(
                                        id="model-coverage-loading",
                                        type="circle",
                                        color="#10b981",
                                        children=[
                                            dag.AgGrid(
                                                id="model-coverage-grid",
                                                rowData=[],
                                                columnDefs=model_cov_column_defs,
                                                defaultColDef={"resizable": True, "sortable": True, "filter": True},
                                                dashGridOptions={"pagination": True, "paginationPageSize": 20, "domLayout": "autoHeight"},
                                                className="ag-theme-alpine-dark",
                                                style={"height": "400px", "width": "100%"}
                                            )
                                        ]
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
                            html.Div(
                                [
                                    html.H5("Column-Level Test Coverage", className="text-white fw-bold mb-3"),
                                    html.P("Columns without tests highlighted in red. Click column headers to sort/filter.", className="text-muted small mb-3"),
                                    dcc.Loading(
                                        id="column-coverage-loading",
                                        type="circle",
                                        color="#10b981",
                                        children=[
                                            dag.AgGrid(
                                                id="column-coverage-grid",
                                                rowData=[],
                                                columnDefs=col_cov_column_defs,
                                                defaultColDef={"resizable": True, "sortable": True, "filter": True},
                                                dashGridOptions={"pagination": True, "paginationPageSize": 25},
                                                className="ag-theme-alpine-dark",
                                                style={"height": "500px", "width": "100%"}
                                            )
                                        ]
                                    )
                                ],
                                className="dark-card p-4 rounded shadow-sm mt-3"
                            )
                        ],
                        label="Column Coverage",
                        tab_id="tab-column-coverage"
                    ),

                    dbc.Tab(
                        [
                            html.Div(
                                [
                                    html.H5("Table Ingestion Parity & Row Counts", className="text-white fw-bold mb-1"),
                                    html.P("Side-by-side comparison of row counts between SQL Server source ingestion and BigQuery destination.", className="text-muted small mb-3"),
                                    dcc.Graph(id="pipeline-ingestion-chart", style={"height": "350px"}),
                                    html.Hr(className="my-4 border-secondary"),
                                    html.H6("Detailed Ingestion Audit Logs", className="text-white fw-bold mb-3"),
                                    dcc.Loading(
                                        id="table-ingestion-loading",
                                        type="circle",
                                        color="#10b981",
                                        children=[
                                            dag.AgGrid(
                                                id="table-ingestion-grid",
                                                rowData=[],
                                                columnDefs=ingestion_column_defs,
                                                defaultColDef={"resizable": True, "sortable": True, "filter": True},
                                                dashGridOptions={"pagination": True, "paginationPageSize": 20},
                                                className="ag-theme-alpine-dark",
                                                style={"height": "400px", "width": "100%"}
                                            )
                                        ]
                                    )
                                ],
                                className="dark-card p-4 rounded shadow-sm mt-3"
                            )
                        ],
                        label="Table Ingestion Counts",
                        tab_id="tab-table-ingestion"
                    ),

                    dbc.Tab(
                        [
                            html.Div(
                                [
                                    html.H5("BigQuery Cost & Query Performance", className="text-white fw-bold mb-1"),
                                    html.P("Monitor daily query volume, slot utilization, and heavy queries from INFORMATION_SCHEMA.", className="text-muted small mb-3"),
                                    dcc.Graph(id="bq-daily-cost-graph", style={"height": "350px"}),
                                    html.Hr(className="my-4 border-secondary"),
                                    html.H6("Top Expensive Queries (Last 7 Days)", className="text-white fw-bold mb-3"),
                                    dcc.Loading(
                                        id="bq-expensive-queries-loading",
                                        type="circle",
                                        color="#10b981",
                                        children=[
                                            dag.AgGrid(
                                                id="bq-expensive-queries-grid",
                                                columnDefs=bq_cost_column_defs,
                                                defaultColDef={"resizable": True, "sortable": True, "filter": True},
                                                dashGridOptions={"pagination": True, "paginationPageSize": 15},
                                                className="ag-theme-alpine-dark",
                                                style={"height": "450px", "width": "100%"}
                                            )
                                        ]
                                    )
                                ],
                                className="dark-card p-4 rounded shadow-sm mt-3"
                            )
                        ],
                        label="BigQuery Costs",
                        tab_id="tab-bq-costs"
                    )
                ],
                id="pipeline-tabs",
                active_tab="tab-execution",
                className="mb-4"
            ),
        ]
    )

# Unified callback to populate KPI cards and active tab data lazily
@callback(
    [
        Output("kpi-source-freshness-val", "children"),
        Output("kpi-latest-load-val", "children"),
        Output("kpi-passed-tests-val", "children"),
        Output("kpi-failed-tests-val", "children"),
        Output("kpi-column-coverage-val", "children"),
        Output("kpi-columns-tested-val", "children"),
        Output("kpi-total-tests-val", "children"),
        Output("kpi-avg-duration-val", "children"),
        Output("kpi-models-100-val", "children"),
        Output("kpi-models-80-val", "children"),
        Output("kpi-models-50-val", "children"),
        Output("kpi-warnings-val", "children"),
        Output("pipeline-execution-grid", "rowData"),
        Output("model-coverage-grid", "rowData"),
        Output("column-coverage-grid", "rowData"),
        Output("pipeline-ingestion-chart", "figure"),
        Output("table-ingestion-grid", "rowData"),
    ],
    [Input("pipeline-tabs", "active_tab")]
)
def update_pipeline_data(active_tab):
    # Load all base summary/metadata needed for KPIs
    df_summary = load_pipeline_health_summary()
    df_source_freshness = load_source_freshness()
    
    # KPI metrics calculations
    freshness_val = f"{df_source_freshness['hours_since_load'].min():.0f}h" if not df_source_freshness.empty else "N/A"
    latest_load_val = pd.to_datetime(df_source_freshness['last_loaded'].max()).strftime('%Y-%m-%d %H:%M UTC') if not df_source_freshness.empty else 'N/A'
    
    passed = df_summary["passed_tests"].iloc[0] if not df_summary.empty else 0
    failed = df_summary["failed_tests"].iloc[0] if not df_summary.empty else 0
    warnings = df_summary["warning_tests"].iloc[0] if not df_summary.empty else 0
    avg_dur = df_summary["avg_model_duration_sec"].iloc[0] if not df_summary.empty else 0.0

    coverage_pct = df_summary["overall_column_coverage_pct"].iloc[0] if not df_summary.empty else 0.0
    total_models = df_summary["total_models"].iloc[0] if not df_summary.empty else 0
    total_columns = df_summary["total_columns"].iloc[0] if not df_summary.empty else 0
    total_tested = df_summary["total_columns_with_tests"].iloc[0] if not df_summary.empty else 0
    total_tests = df_summary["total_tests"].iloc[0] if not df_summary.empty else 0
    models_fully = df_summary["models_fully_covered"].iloc[0] if not df_summary.empty else 0
    models_well = df_summary["models_well_covered"].iloc[0] if not df_summary.empty else 0
    models_poor = df_summary["models_poorly_covered"].iloc[0] if not df_summary.empty else 0

    coverage_color = "success" if coverage_pct >= 90 else ("warning" if coverage_pct >= 70 else "danger")

    kpi_source = html.H4(freshness_val, className="text-white fw-bold mb-0")
    kpi_latest = html.H4(latest_load_val, className="text-white fw-bold mb-0")
    kpi_passed = html.H4(f"{passed:,}", className="text-success fw-bold mb-0")
    kpi_failed = html.H4(f"{failed:,}", className="text-danger fw-bold mb-0")
    kpi_cov = html.H4(f"{coverage_pct:.1f}%", className=f"text-{coverage_color} fw-bold mb-0")
    kpi_tested_cols = html.H4(f"{total_tested:,} / {total_columns:,}", className="text-white fw-bold mb-0")
    kpi_tot_tests = html.H4(f"{total_tests:,}", className="text-info fw-bold mb-0")
    kpi_avg_dur = html.H4(f"{avg_dur:.2f}s", className="text-white fw-bold mb-0")
    
    kpi_m100 = [html.H4(f"{models_fully:,}", className="text-success fw-bold mb-0"), html.Span(f"of {total_models}", className="text-muted small")]
    kpi_m80 = [html.H4(f"{models_well:,}", className="text-warning fw-bold mb-0"), html.Span(f"of {total_models}", className="text-muted small")]
    kpi_m50 = [html.H4(f"{models_poor:,}", className="text-danger fw-bold mb-0"), html.Span(f"of {total_models}", className="text-muted small")]
    kpi_warn = html.H4(f"{warnings:,}", className="text-warning fw-bold mb-0")

    # Fetch data conditionally based on active tab to optimize performance
    exec_logs = load_dbt_execution_logs().to_dict("records") if active_tab == "tab-execution" else dash.no_update
    model_cov = load_model_coverage_details().to_dict("records") if active_tab == "tab-model-coverage" else dash.no_update
    col_cov = load_column_coverage_details().to_dict("records") if active_tab == "tab-column-coverage" else dash.no_update
    
    if active_tab == "tab-table-ingestion":
        df_ingestion = load_table_ingestion_logs()
        ingestion_grid = df_ingestion.to_dict("records") if not df_ingestion.empty else []
        
        if not df_ingestion.empty:
            df_latest = df_ingestion.sort_values("run_timestamp").groupby("table_name", as_index=False).last()
            df_melted = df_latest.melt(
                id_vars=["table_name"],
                value_vars=["source_rows", "destination_rows"],
                var_name="metric_type",
                value_name="row_count"
            )
            df_melted["metric_type"] = df_melted["metric_type"].replace({
                "source_rows": "SQL Server (Source)",
                "destination_rows": "BigQuery (Destination)"
            })
            
            fig_ingestion = px.bar(
                df_melted, x="table_name", y="row_count", color="metric_type", barmode="group", text="row_count",
                template="plotly_dark",
                labels={"table_name": "Table Name", "row_count": "Row Count", "metric_type": "System Layer"},
                color_discrete_map={"SQL Server (Source)": "#3b82f6", "BigQuery (Destination)": "#10b981"}
            )
            fig_ingestion.update_traces(texttemplate='%{text:,}', textposition='outside')
            fig_ingestion.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=30, b=30, l=40, r=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hoverlabel=dict(bgcolor="#1f2937", font_color="#ffffff", bordercolor="#374151")
            )
        else:
            fig_ingestion = go.Figure()
            fig_ingestion.update_layout(
                template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis={"visible": False}, yaxis={"visible": False},
                annotations=[{"text": "No ingestion logs found.", "xref": "paper", "yref": "paper", "showarrow": False, "font": {"color": "#9ca3af"}}]
            )
    else:
        fig_ingestion = dash.no_update
        ingestion_grid = dash.no_update

    return (
        kpi_source, kpi_latest, kpi_passed, kpi_failed, kpi_cov, kpi_tested_cols, 
        kpi_tot_tests, kpi_avg_dur, kpi_m100, kpi_m80, kpi_m50, kpi_warn,
        exec_logs, model_cov, col_cov, fig_ingestion, ingestion_grid
    )

# Existing BQ Cost callback remains independent and lazy-loaded
@callback(
    [
        Output("bq-daily-cost-graph", "figure"),
        Output("bq-expensive-queries-grid", "rowData")
    ],
    [Input("pipeline-tabs", "active_tab")]
)
def update_bq_cost_monitoring(active_tab):
    if active_tab != "tab-bq-costs":
        return dash.no_update, dash.no_update

    df_costs = load_bigquery_cost_metrics(days_back=30)
    df_expensive = load_expensive_queries(limit=25)
    
    if df_costs.empty:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis={"visible": False},
            yaxis={"visible": False},
            annotations=[{
                "text": "No BigQuery job history found in region-us-central1.",
                "xref": "paper", "yref": "paper",
                "showarrow": False,
                "font": {"size": 14, "color": "#9ca3af"}
            }]
        )
    else:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        for job_type in df_costs["job_type"].unique():
            df_subset = df_costs[df_costs["job_type"] == job_type]
            fig.add_trace(
                go.Bar(
                    x=df_subset["execution_date"],
                    y=df_subset["total_queries"],
                    name=f"Queries ({job_type})",
                    marker_color="#3b82f6" if job_type == "QUERY" else "#8b5cf6"
                ),
                secondary_y=False,
            )

        df_trend = df_costs.groupby("execution_date", as_index=False).agg({
            "avg_duration_seconds": "mean",
            "total_slot_minutes": "sum"
        })
        
        fig.add_trace(
            go.Scatter(
                x=df_trend["execution_date"],
                y=df_trend["avg_duration_seconds"],
                name="Avg Duration (s)",
                mode="lines+markers",
                line=dict(color="#10b981", width=3)
            ),
            secondary_y=True,
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            barmode="stack",
            margin=dict(t=30, b=30, l=40, r=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
            hovermode="x unified",
            hoverlabel=dict(bgcolor="#1f2937", font_color="#ffffff", bordercolor="#374151")
        )
        
        fig.update_yaxes(title_text="Total Queries", secondary_y=False, showgrid=True, gridcolor="#374151")
        fig.update_yaxes(title_text="Avg Duration (s)", secondary_y=True, showgrid=False)
        fig.update_xaxes(showgrid=False)

    grid_data = df_expensive.to_dict("records") if not df_expensive.empty else []
    return fig, grid_data
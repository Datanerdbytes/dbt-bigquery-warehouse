import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# pyrefly: ignore [missing-import]
from components.panels import create_grid, loading, panel
from dash import Input, Output, callback, dcc, html

# pyrefly: ignore [missing-import]
from data_loader import (
    load_bigquery_cost_metrics,
    load_column_coverage_details,
    load_dbt_execution_logs,
    load_expensive_queries,
    load_model_coverage_details,
    load_pipeline_health_summary,
    load_source_freshness,
    load_table_ingestion_logs,
)
from plotly.subplots import make_subplots

# pyrefly: ignore [missing-import]
from theme import COLORS, style_figure

# pyrefly: ignore [missing-import]
from utils.helpers import dataframe_value

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


def create_kpi_card(
    title, value_id, value_children, subtitle=None, card_id=None, tooltip_key=None
):
    return html.Div(
        [
            html.H2(title, className="kpi-label"),
            html.Div(value_children, id=value_id, className="kpi-number"),
            html.Small(subtitle, className="panel-description") if subtitle else None,
            (
                dbc.Tooltip(
                    KPI_TOOLTIPS[tooltip_key], target=card_id, placement="bottom"
                )
                if tooltip_key
                else None
            ),
        ],
        id=card_id,
        className="kpi-card",
    )


def layout():
    # Column definitions for grids
    exec_column_defs = [
        {
            "field": "run_timestamp",
            "headerName": "Timestamp",
            "sort": "desc",
            "width": 180,
        },
        {"field": "resource_type", "headerName": "Type", "width": 110},
        {
            "field": "node_name",
            "headerName": "Node / Test Name",
            "flex": 1,
            "filter": True,
        },
        {
            "field": "target_table",
            "headerName": "Target Table",
            "width": 160,
            "filter": True,
        },
        {
            "field": "status",
            "headerName": "Status",
            "width": 120,
            "cellStyle": {
                "styleConditions": [
                    {
                        "condition": "params.value == 'pass' || params.value == 'success'",
                        "style": {"color": COLORS["success"], "fontWeight": "bold"},
                    },
                    {
                        "condition": "params.value == 'fail' || params.value == 'error'",
                        "style": {"color": COLORS["danger"], "fontWeight": "bold"},
                    },
                    {
                        "condition": "params.value == 'warn'",
                        "style": {"color": COLORS["warning"], "fontWeight": "bold"},
                    },
                ]
            },
        },
        {"field": "execution_time_seconds", "headerName": "Duration (s)", "width": 130},
        {"field": "rows_affected", "headerName": "Failed Rows", "width": 130},
        {
            "field": "error_message",
            "headerName": "Error Details",
            "flex": 1.5,
            "tooltipField": "error_message",
        },
    ]

    model_cov_column_defs = [
        {"field": "model_name", "headerName": "Model", "width": 200, "filter": True},
        {"field": "schema", "headerName": "Schema", "width": 100, "filter": True},
        {"field": "total_columns", "headerName": "Total Cols", "width": 100},
        {"field": "columns_with_tests", "headerName": "Tested Cols", "width": 110},
        {
            "field": "column_coverage_pct",
            "headerName": "Coverage %",
            "width": 120,
            "cellRenderer": "agAnimateShowChangeCellRenderer",
            "cellStyle": {
                "styleConditions": [
                    {
                        "condition": "params.value == 100",
                        "style": {"color": COLORS["success"], "fontWeight": "bold"},
                    },
                    {
                        "condition": "params.value >= 80",
                        "style": {"color": COLORS["warning"], "fontWeight": "bold"},
                    },
                    {
                        "condition": "params.value < 50",
                        "style": {"color": COLORS["danger"], "fontWeight": "bold"},
                    },
                ]
            },
        },
        {"field": "total_tests", "headerName": "Total Tests", "width": 110},
    ]

    col_cov_column_defs = [
        {"field": "model_name", "headerName": "Model", "width": 180, "filter": True},
        {"field": "schema", "headerName": "Schema", "width": 90, "filter": True},
        {"field": "column_name", "headerName": "Column", "width": 180, "filter": True},
        {
            "field": "column_description",
            "headerName": "Description",
            "flex": 1,
            "filter": True,
        },
        {"field": "data_type", "headerName": "Type", "width": 100},
        {"field": "test_count", "headerName": "# Tests", "width": 80},
        {
            "field": "test_names",
            "headerName": "Test Names",
            "flex": 1.5,
            "tooltipField": "test_names",
        },
        {
            "field": "has_tests",
            "headerName": "Tested",
            "width": 80,
            "cellRenderer": "agCheckboxCellRenderer",
            "cellStyle": {
                "styleConditions": [
                    {
                        "condition": "params.value == true",
                        "style": {"color": COLORS["success"], "textAlign": "center"},
                    },
                    {
                        "condition": "params.value == false",
                        "style": {
                            "color": COLORS["danger"],
                            "textAlign": "center",
                            "fontWeight": "bold",
                        },
                    },
                ]
            },
        },
    ]

    ingestion_column_defs = [
        {
            "field": "run_timestamp",
            "headerName": "Timestamp",
            "sort": "desc",
            "width": 180,
        },
        {
            "field": "resource_type",
            "headerName": "Ingestion Type",
            "width": 160,
            "filter": True,
        },
        {
            "field": "table_name",
            "headerName": "Source / Table Name",
            "width": 200,
            "filter": True,
        },
        {
            "field": "target_table",
            "headerName": "Destination Table",
            "flex": 1,
            "filter": True,
        },
        {
            "field": "rows_inserted",
            "headerName": "Rows Inserted",
            "width": 150,
            "type": "numericColumn",
            "cellStyle": {"fontWeight": "bold"},
        },
        {"field": "duration_seconds", "headerName": "Duration (s)", "width": 130},
        {
            "field": "status",
            "headerName": "Status",
            "width": 110,
            "cellStyle": {
                "styleConditions": [
                    {
                        "condition": "params.value == 'pass' || params.value == 'success'",
                        "style": {"color": COLORS["success"], "fontWeight": "bold"},
                    },
                    {
                        "condition": "params.value == 'fail' || params.value == 'error'",
                        "style": {"color": COLORS["danger"], "fontWeight": "bold"},
                    },
                ]
            },
        },
    ]

    bq_cost_column_defs = [
        {
            "field": "creation_time",
            "headerName": "Timestamp",
            "sort": "desc",
            "width": 180,
        },
        {
            "field": "user_email",
            "headerName": "User / Service Account",
            "width": 220,
            "filter": True,
        },
        {
            "field": "gb_processed",
            "headerName": "GB Processed",
            "width": 140,
            "type": "numericColumn",
        },
        {
            "field": "slot_seconds",
            "headerName": "Slot Seconds",
            "width": 130,
            "type": "numericColumn",
        },
        {"field": "duration_seconds", "headerName": "Duration (s)", "width": 120},
        {"field": "query", "headerName": "Query Text", "flex": 2, "filter": True},
    ]

    return html.Div(
        [
            loading(
                html.Div(
                    [
                        create_kpi_card(
                            "Source freshness",
                            "kpi-source-freshness-val",
                            "—",
                            card_id="card-source-freshness",
                            tooltip_key="source-freshness",
                        ),
                        create_kpi_card(
                            "Passed tests",
                            "kpi-passed-tests-val",
                            "—",
                            card_id="card-passed-tests",
                            tooltip_key="passed-tests",
                        ),
                        create_kpi_card(
                            "Failed tests",
                            "kpi-failed-tests-val",
                            "—",
                            card_id="card-failed-tests",
                            tooltip_key="failed-tests",
                        ),
                        create_kpi_card(
                            "Column coverage",
                            "kpi-column-coverage-val",
                            "—",
                            card_id="card-column-coverage",
                            tooltip_key="column-coverage",
                        ),
                    ],
                    className="kpi-grid",
                ),
                "pipeline-kpi-loading",
            ),
            html.Details(
                [
                    html.Summary("More pipeline metrics"),
                    html.Div(
                        [
                            create_kpi_card(
                                "Latest load",
                                "kpi-latest-load-val",
                                "—",
                                card_id="card-latest-load",
                                tooltip_key="latest-load",
                            ),
                            create_kpi_card(
                                "Columns tested",
                                "kpi-columns-tested-val",
                                "—",
                                card_id="card-columns-tested",
                                tooltip_key="columns-tested",
                            ),
                            create_kpi_card(
                                "Total tests",
                                "kpi-total-tests-val",
                                "—",
                                card_id="card-total-tests",
                                tooltip_key="total-tests",
                            ),
                            create_kpi_card(
                                "Average duration",
                                "kpi-avg-duration-val",
                                "—",
                                card_id="card-avg-duration",
                                tooltip_key="avg-duration",
                            ),
                            create_kpi_card(
                                "Models at 100%",
                                "kpi-models-100-val",
                                "—",
                                card_id="card-models-100",
                                tooltip_key="models-100",
                            ),
                            create_kpi_card(
                                "Models at 80%+",
                                "kpi-models-80-val",
                                "—",
                                card_id="card-models-80",
                                tooltip_key="models-80",
                            ),
                            create_kpi_card(
                                "Models below 50%",
                                "kpi-models-50-val",
                                "—",
                                card_id="card-models-50",
                                tooltip_key="models-50",
                            ),
                            create_kpi_card(
                                "Warnings",
                                "kpi-warnings-val",
                                "—",
                                card_id="card-warnings",
                                tooltip_key="warnings",
                            ),
                        ],
                        className="kpi-grid secondary-kpis",
                    ),
                ],
                className="pipeline-details",
            ),
            dbc.Tabs(
                [
                    dbc.Tab(
                        panel(
                            "Execution logs",
                            [
                                loading(
                                    create_grid(
                                        exec_column_defs,
                                        grid_id="pipeline-execution-grid",
                                        class_name="pipeline-grid",
                                    ),
                                    "pipeline-execution-grid-loading",
                                )
                            ],
                            description="Latest 200 model and test executions.",
                        ),
                        label="Execution logs",
                        tab_id="tab-execution",
                    ),
                    dbc.Tab(
                        panel(
                            "Model coverage",
                            [
                                loading(
                                    dcc.Graph(
                                        id="model-coverage-chart",
                                        config={
                                            "displayModeBar": False,
                                            "responsive": True,
                                        },
                                    ),
                                    "model-coverage-chart-loading",
                                ),
                                loading(
                                    create_grid(
                                        model_cov_column_defs,
                                        grid_id="model-coverage-grid",
                                        class_name="pipeline-grid",
                                    ),
                                    "model-coverage-grid-loading",
                                ),
                            ],
                            description="Test coverage by model.",
                        ),
                        label="Model coverage",
                        tab_id="tab-model-coverage",
                    ),
                    dbc.Tab(
                        panel(
                            "Column coverage",
                            [
                                loading(
                                    dcc.Graph(
                                        id="column-coverage-chart",
                                        config={
                                            "displayModeBar": False,
                                            "responsive": True,
                                        },
                                    ),
                                    "column-coverage-chart-loading",
                                ),
                                loading(
                                    create_grid(
                                        col_cov_column_defs,
                                        grid_id="column-coverage-grid",
                                        class_name="pipeline-grid",
                                    ),
                                    "column-coverage-grid-loading",
                                ),
                            ],
                            description="Inspect tested and untested columns.",
                        ),
                        label="Column coverage",
                        tab_id="tab-column-coverage",
                    ),
                    dbc.Tab(
                        panel(
                            "Ingestion",
                            [
                                loading(
                                    dcc.Graph(
                                        id="pipeline-ingestion-chart",
                                        config={
                                            "displayModeBar": False,
                                            "responsive": True,
                                        },
                                    ),
                                    "pipeline-ingestion-chart-loading",
                                ),
                                loading(
                                    create_grid(
                                        ingestion_column_defs,
                                        grid_id="table-ingestion-grid",
                                        class_name="pipeline-grid",
                                    ),
                                    "table-ingestion-grid-loading",
                                ),
                            ],
                            description="Latest table snapshots; audit history shows the latest 200 records from the past 30 days.",
                        ),
                        label="Ingestion",
                        tab_id="tab-table-ingestion",
                    ),
                    dbc.Tab(
                        panel(
                            "BigQuery costs",
                            [
                                loading(
                                    dcc.Graph(
                                        id="bq-daily-cost-graph",
                                        config={
                                            "displayModeBar": False,
                                            "responsive": True,
                                        },
                                    ),
                                    "bq-daily-cost-graph-loading",
                                ),
                                loading(
                                    create_grid(
                                        bq_cost_column_defs,
                                        grid_id="bq-expensive-queries-grid",
                                        class_name="pipeline-grid",
                                    ),
                                    "bq-expensive-queries-grid-loading",
                                ),
                            ],
                            description="Query activity over 30 days and the 25 most expensive queries from the past 7 days.",
                        ),
                        label="BigQuery costs",
                        tab_id="tab-bq-costs",
                    ),
                ],
                id="pipeline-tabs",
                active_tab="tab-execution",
                className="pipeline-tabs",
            ),
        ],
        className="dashboard-container pipeline-container",
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
        Output("model-coverage-chart", "figure"),
        Output("model-coverage-grid", "rowData"),
        Output("column-coverage-chart", "figure"),
        Output("column-coverage-grid", "rowData"),
        Output("pipeline-ingestion-chart", "figure"),
        Output("table-ingestion-grid", "rowData"),
    ],
    [Input("pipeline-tabs", "active_tab")],
)
def update_pipeline_data(active_tab):
    # Load all base summary/metadata needed for KPIs
    df_summary = load_pipeline_health_summary()
    df_source_freshness = load_source_freshness()

    # KPI metrics calculations
    freshness_hours = pd.Series(dtype="float64")
    load_dates = pd.Series(dtype="datetime64[ns, UTC]")
    if df_source_freshness is not None and not df_source_freshness.empty:
        freshness_hours = pd.to_numeric(
            df_source_freshness["hours_since_load"], errors="coerce"
        ).dropna()
        load_dates = pd.to_datetime(
            df_source_freshness["last_loaded"], errors="coerce", utc=True
        ).dropna()
    freshness_val = (
        f"{freshness_hours.max():.0f}h" if not freshness_hours.empty else "N/A"
    )
    latest_load_val = (
        load_dates.max().strftime("%Y-%m-%d %H:%M UTC")
        if not load_dates.empty
        else "N/A"
    )

    passed = dataframe_value(df_summary, "passed_tests", 0)
    failed = dataframe_value(df_summary, "failed_tests", 0)
    warnings = dataframe_value(df_summary, "warning_tests", 0)
    avg_dur = dataframe_value(df_summary, "avg_model_duration_sec", 0.0)

    coverage_pct = dataframe_value(df_summary, "overall_column_coverage_pct", 0.0)
    total_models = dataframe_value(df_summary, "total_models", 0)
    total_columns = dataframe_value(df_summary, "total_columns", 0)
    total_tested = dataframe_value(df_summary, "total_columns_with_tests", 0)
    total_tests = dataframe_value(df_summary, "total_tests", 0)
    models_fully = dataframe_value(df_summary, "models_fully_covered", 0)
    models_well = dataframe_value(df_summary, "models_well_covered", 0)
    models_poor = dataframe_value(df_summary, "models_poorly_covered", 0)

    coverage_color = (
        "success"
        if coverage_pct >= 90
        else ("warning" if coverage_pct >= 70 else "danger")
    )

    kpi_source = html.H4(freshness_val, className="text-white fw-bold mb-0")
    kpi_latest = html.H4(latest_load_val, className="text-white fw-bold mb-0")
    kpi_passed = html.H4(f"{passed:,}", className="text-success fw-bold mb-0")
    kpi_failed = html.H4(f"{failed:,}", className="text-danger fw-bold mb-0")
    kpi_cov = html.H4(
        f"{coverage_pct:.1f}%", className=f"text-{coverage_color} fw-bold mb-0"
    )
    kpi_tested_cols = html.H4(
        f"{total_tested:,} / {total_columns:,}", className="text-white fw-bold mb-0"
    )
    kpi_tot_tests = html.H4(f"{total_tests:,}", className="text-info fw-bold mb-0")
    kpi_avg_dur = html.H4(f"{avg_dur:.2f}s", className="text-white fw-bold mb-0")

    kpi_m100 = [
        html.H4(f"{models_fully:,}", className="text-success fw-bold mb-0"),
        html.Span(f"of {total_models}", className="text-muted small"),
    ]
    kpi_m80 = [
        html.H4(f"{models_well:,}", className="text-warning fw-bold mb-0"),
        html.Span(f"of {total_models}", className="text-muted small"),
    ]
    kpi_m50 = [
        html.H4(f"{models_poor:,}", className="text-danger fw-bold mb-0"),
        html.Span(f"of {total_models}", className="text-muted small"),
    ]
    kpi_warn = html.H4(f"{warnings:,}", className="text-warning fw-bold mb-0")

    # Fetch data conditionally based on active tab to optimize performance
    exec_logs = (
        load_dbt_execution_logs().to_dict("records")
        if active_tab == "tab-execution"
        else dash.no_update
    )

    # Model Coverage Tab Processing & Chart Generation
    if active_tab == "tab-model-coverage":
        df_model_cov = load_model_coverage_details()
        model_cov = df_model_cov.to_dict("records") if not df_model_cov.empty else []

        if not df_model_cov.empty:
            # Explicitly calculate coverage percentage to ensure it matches the table
            if (
                "tested_columns" in df_model_cov.columns
                and "total_columns" in df_model_cov.columns
            ):
                df_model_cov["calc_coverage_pct"] = (
                    df_model_cov["tested_columns"]
                    / df_model_cov["total_columns"].replace(0, 1)
                ) * 100
                cov_col = "calc_coverage_pct"
            else:
                # Fallback search for any existing percentage/coverage column
                cov_col = next(
                    (
                        col
                        for col in df_model_cov.columns
                        if any(k in col.lower() for k in ["cov", "pct", "percent"])
                    ),
                    None,
                )
                if cov_col and df_model_cov[cov_col].max() <= 1.0:
                    df_model_cov[cov_col] = df_model_cov[cov_col] * 100

            df_sorted = df_model_cov.sort_values(cov_col, ascending=True)

            fig_model_cov = px.bar(
                df_sorted,
                x=cov_col,
                y="model_name",
                orientation="h",
                template="plotly_dark",
                text=df_sorted[cov_col].apply(lambda x: f"{x:.2f}%"),
                labels={cov_col: "Coverage Percentage (%)", "model_name": "Model Name"},
                color=cov_col,
                color_continuous_scale=[
                    COLORS["danger"],
                    COLORS["warning"],
                    COLORS["success"],
                ],
                range_color=[0, 100],  # <--- Fixes the scale from absolute 0% to 100%
            )

            fig_model_cov.update_traces(textposition="outside")
            fig_model_cov.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=30, b=30, l=120, r=40),
                coloraxis_showscale=False,
                xaxis=dict(range=[0, 115], showgrid=True, gridcolor=COLORS["border"]),
                yaxis=dict(showgrid=False),
                hoverlabel=dict(
                    bgcolor=COLORS["border"],
                    font_color=COLORS["text"],
                    bordercolor=COLORS["border"],
                ),
            )
        else:
            fig_model_cov = go.Figure()
            fig_model_cov.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis={"visible": False},
                yaxis={"visible": False},
                annotations=[
                    {
                        "text": "No model coverage records found.",
                        "xref": "paper",
                        "yref": "paper",
                        "showarrow": False,
                        "font": {"color": COLORS["muted"]},
                    }
                ],
            )
    else:
        fig_model_cov = dash.no_update
        model_cov = dash.no_update

    # Column Coverage Tab Processing
    if active_tab == "tab-column-coverage":
        df_col_cov = load_column_coverage_details()
        col_cov = df_col_cov.to_dict("records") if not df_col_cov.empty else []

        if not df_col_cov.empty:
            df_grouped = df_col_cov.groupby(
                ["model_name", "has_tests"], as_index=False
            ).size()
            df_grouped["status"] = df_grouped["has_tests"].map(
                {True: "Tested Columns", False: "Untested Columns"}
            )

            fig_col_cov = px.bar(
                df_grouped,
                x="model_name",
                y="size",
                color="status",
                barmode="stack",
                template="plotly_dark",
                labels={
                    "model_name": "Model Name",
                    "size": "Column Count",
                    "status": "Coverage Status",
                },
                color_discrete_map={
                    "Tested Columns": COLORS["success"],
                    "Untested Columns": COLORS["danger"],
                },
            )
            fig_col_cov.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=30, b=30, l=40, r=10),
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
                ),
                hoverlabel=dict(
                    bgcolor=COLORS["border"],
                    font_color=COLORS["text"],
                    bordercolor=COLORS["border"],
                ),
            )
        else:
            fig_col_cov = go.Figure()
            fig_col_cov.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis={"visible": False},
                yaxis={"visible": False},
                annotations=[
                    {
                        "text": "No column coverage records found.",
                        "xref": "paper",
                        "yref": "paper",
                        "showarrow": False,
                        "font": {"color": COLORS["muted"]},
                    }
                ],
            )
    else:
        fig_col_cov = dash.no_update
        col_cov = dash.no_update

    # Table Ingestion Tab Processing
    if active_tab == "tab-table-ingestion":
        df_ingestion = load_table_ingestion_logs()
        ingestion_grid = (
            df_ingestion.to_dict("records") if not df_ingestion.empty else []
        )

        df_latest = load_table_ingestion_logs(latest_only=True)
        if not df_latest.empty:
            df_melted = df_latest.melt(
                id_vars=["table_name"],
                value_vars=["source_rows", "destination_rows"],
                var_name="metric_type",
                value_name="row_count",
            )
            df_melted["metric_type"] = df_melted["metric_type"].replace(
                {
                    "source_rows": "SQL Server (Source)",
                    "destination_rows": "BigQuery (Destination)",
                }
            )

            fig_ingestion = px.bar(
                df_melted,
                x="table_name",
                y="row_count",
                color="metric_type",
                barmode="group",
                text="row_count",
                template="plotly_dark",
                labels={
                    "table_name": "Table Name",
                    "row_count": "Row Count",
                    "metric_type": "System Layer",
                },
                color_discrete_map={
                    "SQL Server (Source)": COLORS["accent"],
                    "BigQuery (Destination)": COLORS["success"],
                },
            )
            fig_ingestion.update_traces(
                texttemplate="%{text:,}", textposition="outside"
            )
            fig_ingestion.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=30, b=30, l=40, r=10),
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
                ),
                hoverlabel=dict(
                    bgcolor=COLORS["border"],
                    font_color=COLORS["text"],
                    bordercolor=COLORS["border"],
                ),
            )
        else:
            fig_ingestion = go.Figure()
            fig_ingestion.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis={"visible": False},
                yaxis={"visible": False},
                annotations=[
                    {
                        "text": "No ingestion logs found.",
                        "xref": "paper",
                        "yref": "paper",
                        "showarrow": False,
                        "font": {"color": COLORS["muted"]},
                    }
                ],
            )
    else:
        fig_ingestion = dash.no_update
        ingestion_grid = dash.no_update

    if fig_model_cov is not dash.no_update:
        style_figure(fig_model_cov, height=340)
    if fig_col_cov is not dash.no_update:
        style_figure(fig_col_cov, height=320)
    if fig_ingestion is not dash.no_update:
        style_figure(fig_ingestion, height=320)

    # Final Return matching the exact 19 outputs order
    return (
        kpi_source,
        kpi_latest,
        kpi_passed,
        kpi_failed,
        kpi_cov,
        kpi_tested_cols,
        kpi_tot_tests,
        kpi_avg_dur,
        kpi_m100,
        kpi_m80,
        kpi_m50,
        kpi_warn,
        exec_logs,
        fig_model_cov,
        model_cov,
        fig_col_cov,
        col_cov,
        fig_ingestion,
        ingestion_grid,
    )


# Existing BQ Cost callback remains independent and lazy-loaded
@callback(
    [
        Output("bq-daily-cost-graph", "figure"),
        Output("bq-expensive-queries-grid", "rowData"),
    ],
    [Input("pipeline-tabs", "active_tab")],
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
            annotations=[
                {
                    "text": "No BigQuery job history found in region-us-central1.",
                    "xref": "paper",
                    "yref": "paper",
                    "showarrow": False,
                    "font": {"size": 14, "color": COLORS["muted"]},
                }
            ],
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
                    marker_color=(
                        COLORS["accent"] if job_type == "QUERY" else COLORS["purple"]
                    ),
                ),
                secondary_y=False,
            )

        df_trend = df_costs.groupby("execution_date", as_index=False).agg(
            {"avg_duration_seconds": "mean", "total_slot_minutes": "sum"}
        )

        fig.add_trace(
            go.Scatter(
                x=df_trend["execution_date"],
                y=df_trend["avg_duration_seconds"],
                name="Avg Duration (s)",
                mode="lines+markers",
                line=dict(color=COLORS["success"], width=3),
            ),
            secondary_y=True,
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            barmode="stack",
            margin=dict(t=30, b=30, l=40, r=40),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1
            ),
            hovermode="x unified",
            hoverlabel=dict(
                bgcolor=COLORS["border"],
                font_color=COLORS["text"],
                bordercolor=COLORS["border"],
            ),
        )

        fig.update_yaxes(
            title_text="Total Queries",
            secondary_y=False,
            showgrid=True,
            gridcolor=COLORS["border"],
        )
        fig.update_yaxes(
            title_text="Avg Duration (s)", secondary_y=True, showgrid=False
        )
        fig.update_xaxes(showgrid=False)

    grid_data = df_expensive.to_dict("records") if not df_expensive.empty else []
    return style_figure(fig, height=320), grid_data

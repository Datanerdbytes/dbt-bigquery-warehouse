import dash
import dash_ag_grid as dag
from dash import html, dcc, callback, Input, Output, dash_table
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
from utils.helpers import create_trend_badge, filter_dataframe, format_compact_number
from data_loader import load_and_prep_data
from components.filter_bar import create_filter_bar
from components.kpi_bar import create_kpi_bar

# Register Page
dash.register_page(__name__, path="/customers", name="Customer 360")

def layout():
    # Load cached options inside layout function to build initial dropdowns dynamically
    df_merged, min_data_date, max_data_date, category_options, country_options = load_and_prep_data()

    return html.Div(
    className="dashboard-container py-3",
    children=[
        dbc.Container(
            [
                # Row 1: Filter Control Bar
                create_filter_bar(
                    df_merged,
                    date_picker_id="c360-date-picker",
                    category_dropdown_id="c360-category-dropdown",
                    country_dropdown_id="c360-country-dropdown"
                ),
                # Row 2: KPI Cards
                create_kpi_bar([
                    ("ACTIVE CUSTOMERS", "c360-kpi-active-cust"),
                    ("AVG SPEND / CUST", "c360-kpi-avg-spend"),
                    ("AVG ORDER FREQ", "c360-kpi-avg-freq"),
                    ("REPEAT RATE", "c360-kpi-repeat-rate"),
                ]),

                # Row 3: RFM Segmentation & Spend Distribution
                dbc.Row(
                    [
                        dbc.Col(
                            html.Div(
                                [
                                    html.H5("Customer RFM Segmentation", className="fw-bold text-light mb-2"),
                                    dcc.Graph(id="c360-rfm-segment-graph", config={"displayModeBar": False})
                                ],
                                className="dark-card p-3 rounded shadow-sm mb-3"
                            ),
                            width=12, lg=6
                        ),
                        dbc.Col(
                            html.Div(
                                [
                                    html.H5("Customer Spend Distribution (CLV)", className="fw-bold text-light mb-2"),
                                    dcc.Graph(id="c360-spend-dist-graph", config={"displayModeBar": False})
                                ],
                                className="dark-card p-3 rounded shadow-sm mb-3"
                            ),
                            width=12, lg=6
                        ),
                    ]
                ),

                # Row 4: High Value Table & Active Customer Trend
                dbc.Row(
                    [
                        dbc.Col(
                            html.Div(
                                [
                                    html.H5("Top High-Value Champions", className="fw-bold text-white mb-2"),
                                    html.Div(id="c360-top-customers-table-container")
                                ],
                                className="dark-card p-3 rounded shadow-sm mb-3"
                            ),
                            width=12, lg=6
                        ),
                        dbc.Col(
                            html.Div(
                                [
                                    html.H5("Active Customer Trend", className="fw-bold text-white mb-2"),
                                    dcc.Graph(id="c360-cust-trend-graph", config={"displayModeBar": False})
                                ],
                                className="dark-card p-3 rounded shadow-sm mb-3"
                            ),
                            width=12, lg=6
                        ),
                    ]
                )
            ],
            fluid=True
        )
    ]
)

# --- FILTER STORE SYNC CALLBACK ---
@callback(
    Output("global-filter-store", "data", allow_duplicate=True),
    [
        Input("c360-date-picker", "start_date"),
        Input("c360-date-picker", "end_date"),
        Input("c360-category-dropdown", "value"),
        Input("c360-country-dropdown", "value"),
    ],
    prevent_initial_call=True
)
def sync_c360_filters_to_store(start_date, end_date, category, country):
    return {
        "start_date": start_date,
        "end_date": end_date,
        "category": category,
        "country": country
    }

# --- KPI Callback ---
@callback(
    [
        # Values (Main Numbers)
        Output("c360-kpi-active-cust-value", "children"),
        Output("c360-kpi-avg-spend-value", "children"),
        Output("c360-kpi-avg-freq-value", "children"),
        Output("c360-kpi-repeat-rate-value", "children"),
        # Badges
        Output("c360-kpi-active-cust-badge", "children"),
        Output("c360-kpi-avg-spend-badge", "children"),
        Output("c360-kpi-avg-freq-badge", "children"),
        Output("c360-kpi-repeat-rate-badge", "children"),
        # Tooltips
        Output("c360-kpi-active-cust-tooltip", "children"),
        Output("c360-kpi-avg-spend-tooltip", "children"),
        Output("c360-kpi-avg-freq-tooltip", "children"),
        Output("c360-kpi-repeat-rate-tooltip", "children"),
    ],
    Input("global-filter-store", "data")
)
def update_customer_kpis(filter_data):
    empty_badge = dbc.Badge("N/A", color="secondary", className="small")

    if not filter_data:
        return "0", "$0", "0.00", "0%", empty_badge, empty_badge, empty_badge, empty_badge, "", "", "", ""

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    if not start_date or not end_date:
        return "0", "$0", "0.00", "0%", empty_badge, empty_badge, empty_badge, empty_badge, "", "", "", ""

    df_merged, _, _, _, _ = load_and_prep_data()

    # Parse current period dates
    curr_start = pd.to_datetime(start_date)
    curr_end = pd.to_datetime(end_date)
    date_diff = curr_end - curr_start

    # Calculate previous period dates of equal length
    prev_end = curr_start - pd.Timedelta(days=1)
    prev_start = prev_end - date_diff

    # Filter current & previous datasets
    curr_df = filter_dataframe(df_merged, curr_start, curr_end, selected_category, selected_country)
    prev_df = filter_dataframe(df_merged, prev_start, prev_end, selected_category, selected_country)

    if curr_df.empty:
        return "0", "$0", "0.00", "0%", empty_badge, empty_badge, empty_badge, empty_badge, "No data", "No data", "No data", "No data"

    # --- Compute Current Metrics ---
    curr_summary = curr_df.groupby("customer_key").agg(
        total_spend=("gross_sales_amount", "sum"),
        total_orders=("order_number", "nunique"),
        total_units=("quantity", "sum")
    ).reset_index()

    curr_cust = len(curr_summary)
    curr_spend = curr_summary["total_spend"].sum() / curr_cust if curr_cust > 0 else 0
    curr_freq = curr_summary["total_orders"].sum() / curr_cust if curr_cust > 0 else 0
    curr_repeat_cnt = (curr_summary["total_orders"] > 1).sum()
    curr_repeat_rate = (curr_repeat_cnt / curr_cust * 100) if curr_cust > 0 else 0

    # --- Compute Previous Metrics ---
    if not prev_df.empty:
        prev_summary = prev_df.groupby("customer_key").agg(
            total_spend=("gross_sales_amount", "sum"),
            total_orders=("order_number", "nunique")
        ).reset_index()

        prev_cust = len(prev_summary)
        prev_spend = prev_summary["total_spend"].sum() / prev_cust if prev_cust > 0 else 0
        prev_freq = prev_summary["total_orders"].sum() / prev_cust if prev_cust > 0 else 0
        prev_repeat_cnt = (prev_summary["total_orders"] > 1).sum()
        prev_repeat_rate = (prev_repeat_cnt / prev_cust * 100) if prev_cust > 0 else 0
    else:
        prev_cust = prev_spend = prev_freq = prev_repeat_rate = 0

    # Generate dynamic soft badges matching overview.py styling
    badge_cust = create_trend_badge(curr_cust, prev_cust)
    badge_spend = create_trend_badge(curr_spend, prev_spend)
    badge_freq = create_trend_badge(curr_freq, prev_freq)
    badge_repeat = create_trend_badge(curr_repeat_rate, prev_repeat_rate)

    # Tooltips
    single_order_cust = curr_cust - curr_repeat_cnt
    max_spend = curr_summary["total_spend"].max() if not curr_summary.empty else 0
    median_spend = curr_summary["total_spend"].median() if not curr_summary.empty else 0

    tt_cust = [html.Div(f"• Single-Order Cust: {single_order_cust:,}", className="text-start"), html.Div(f"• Repeat Cust: {curr_repeat_cnt:,}", className="text-start")]
    tt_spend = [html.Div(f"• Max Spend: ${max_spend:,.0f}", className="text-start"), html.Div(f"• Median Spend: ${median_spend:,.0f}", className="text-start")]
    tt_freq = [html.Div(f"• Total Orders: {curr_summary['total_orders'].sum():,}", className="text-start"), html.Div(f"• Units/Cust: {(curr_summary['total_units'].sum()/curr_cust):,.1f}", className="text-start")]
    tt_repeat = [html.Div(f"• Repeat Count: {curr_repeat_cnt:,}", className="text-start"), html.Div(f"• Single Count: {single_order_cust:,}", className="text-start")]

    return (
        f"{curr_cust:,}",
        f"${curr_spend:,.0f}",
        f"{curr_freq:,.2f}",
        f"{curr_repeat_rate:.1f}%",
        badge_cust,
        badge_spend,
        badge_freq,
        badge_repeat,
        tt_cust,
        tt_spend,
        tt_freq,
        tt_repeat,
    )


# --- Visual 1: RFM Segmentation ---
@callback(
    Output("c360-rfm-segment-graph", "figure"),
    Input("global-filter-store", "data")
)
def update_rfm_segments(filter_data):
    if not filter_data:
        return px.bar(title="No Data")

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    df_merged, _, _, _, _ = load_and_prep_data()
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

    if filtered_df.empty:
        return px.bar(title="No Data")

    max_ref_date = pd.to_datetime(end_date)
    filtered_df["order_date"] = pd.to_datetime(filtered_df["order_date"])

    rfm = (
        filtered_df.groupby("customer_key")
        .agg(
            recency=("order_date", lambda x: (max_ref_date - x.max()).days),
            frequency=("order_number", "nunique"),
            monetary=("gross_sales_amount", "sum")
        )
        .reset_index()
    )

    def classify_rfm(row):
        if row["frequency"] >= 3 and row["recency"] <= 30:
            return "Champions"
        elif row["frequency"] >= 2 and row["recency"] <= 60:
            return "Loyal Customers"
        elif row["recency"] > 90:
            return "Hibernating / Lost"
        else:
            return "Promising / Recent"

    rfm["Segment"] = rfm.apply(classify_rfm, axis=1)
    seg_counts = rfm["Segment"].value_counts().reset_index()
    seg_counts.columns = ["Segment", "Customer Count"]

    color_map = {
        "Champions": "#10b981",
        "Loyal Customers": "#3b82f6",
        "Promising / Recent": "#f59e0b",
        "Hibernating / Lost": "#ef4444"
    }

    fig = px.bar(
        seg_counts,
        x="Customer Count",
        y="Segment",
        orientation="h",
        color="Segment",
        color_discrete_map=color_map
    )

    fig.update_traces(hovertemplate="<b>Segment:</b> %{y}<br><b>Customers:</b> %{x:,}<extra></extra>")
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=True, gridcolor="#1f2937", tickfont=dict(color="#9ca3af")),
        yaxis=dict(showgrid=False, tickfont=dict(color="#9ca3af")),
        showlegend=False,
        height=320
    )

    return fig


# --- Visual 2: Spend Distribution ---
@callback(
    Output("c360-spend-dist-graph", "figure"),
    Input("global-filter-store", "data")
)
def update_spend_distribution(filter_data):
    if not filter_data:
        return px.histogram(title="No Data")

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    df_merged, _, _, _, _ = load_and_prep_data()
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

    if filtered_df.empty:
        return px.histogram(title="No Data")

    cust_spend = filtered_df.groupby("customer_key")["gross_sales_amount"].sum().reset_index()

    fig = px.histogram(
        cust_spend,
        x="gross_sales_amount",
        nbins=30,
        labels={"gross_sales_amount": "Total Customer Spend ($)", "count": "Customer Count"},
        color_discrete_sequence=["#10b981"]
    )

    fig.update_traces(hovertemplate="<b>Spend Range:</b> %{x}<br><b>Customers:</b> %{y}<extra></extra>")

    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(showgrid=True, gridcolor="#1f2937", tickfont=dict(color="#9ca3af")),
        xaxis=dict(showgrid=False, tickprefix="$", tickfont=dict(color="#9ca3af")),
        height=320
    )

    return fig


# --- Visual 3: Top High-Value Customers Table ---
@callback(
    Output("c360-top-customers-table-container", "children"),
    Input("global-filter-store", "data")
)
def update_top_customers_table(filter_data):
    if not filter_data:
        return html.Div("No transactions found for selection.", className="text-muted p-3 text-center")

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    df_merged, _, _, _, _ = load_and_prep_data()
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

    if filtered_df.empty:
        return html.Div("No transactions found for selection.", className="text-muted p-3 text-center")

    top_cust = (
        filtered_df.groupby(["first_name", "last_name", "country"])
        .agg(
            total_spend=("gross_sales_amount", "sum"),
            total_orders=("order_number", "nunique")
        )
        .reset_index()
        .sort_values(by="total_spend", ascending=False)
        .head(10)
    )

    top_cust["customer_name"] = top_cust["first_name"].fillna("") + " " + top_cust["last_name"].fillna("")

    column_defs = [
        {"field": "customer_name", "headerName": "Customer"},
        {"field": "country", "headerName": "Country"},
        {"field": "total_orders", "headerName": "Orders", "type": "rightAligned"},
        {
            "field": "total_spend", 
            "headerName": "Total Spend", 
            "type": "rightAligned",
            "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"}
        },
    ]

    grid = dag.AgGrid(
        rowData=top_cust.to_dict("records"),
        columnDefs=column_defs,
        dashGridOptions={
            "theme": "themeBalham", 
            "animateRows": True, 
            "pagination": True, 
            "paginationPageSize": 10
        },
        columnSize="responsiveSizeToFit",
        defaultColDef={"filter": True, "sortable": True},
        style={"height": "320px", "width": "100%"}
    )

    return grid


# --- Visual 4: Active Customer Trend ---
@callback(
    Output("c360-cust-trend-graph", "figure"),
    Input("global-filter-store", "data")
)
def update_customer_trend(filter_data):
    if not filter_data:
        return px.line(title="No Data")

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    df_merged, _, _, _, _ = load_and_prep_data()
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)
    
    if filtered_df.empty:
        return px.line(title="No Data")

    df_trend = filtered_df.copy()
    df_trend["year_month"] = pd.to_datetime(df_trend["order_date"]).dt.to_period("M").dt.to_timestamp()

    monthly_cust = (
        df_trend.groupby("year_month")["customer_key"]
        .nunique()
        .reset_index(name="active_customers")
    )

    fig = px.line(
        monthly_cust,
        x="year_month",
        y="active_customers",
        markers=True,
        labels={"year_month": "Month", "active_customers": "Active Customers"},
        color_discrete_sequence=["#3b82f6"]
    )

    fig.update_traces(
        mode="lines+markers",
        line=dict(width=3, color="#3b82f6"),
        marker=dict(size=6, color="#60a5fa"),
        hovertemplate="<b>Date:</b> %{x|%b %Y}<br><b>Active Cust:</b> %{y:,}<extra></extra>"
    )

    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(showgrid=True, gridcolor="#1f2937", tickfont=dict(color="#9ca3af")),
        xaxis=dict(showgrid=False, tickfont=dict(color="#9ca3af")),
        height=320
    )

    return fig

import dash
import dash_ag_grid as dag
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
from utils.helpers import create_trend_badge, filter_dataframe, format_compact_number
from data_loader import get_prepared_dataset
from components.filter_bar import create_filter_bar
from components.kpi_bar import create_kpi_bar
from components.panels import loading, panel, chart_panel, create_grid
from theme import COLORS, style_figure

# Register Page
dash.register_page(__name__, path="/customers", name="Customer 360")


def layout():
    return html.Div(
        [
            html.Div(id="c360-page-loaded", hidden=True),
            html.Div(
                id="c360-filter-bar-container",
                children=create_filter_bar(
                    pd.DataFrame(),
                    date_picker_id="c360-date-picker",
                    category_dropdown_id="c360-category-dropdown",
                    country_dropdown_id="c360-country-dropdown",
                ),
            ),
            loading(
                create_kpi_bar(
                    [
                        ("Active customers", "c360-kpi-active-cust"),
                        ("Average spend", "c360-kpi-avg-spend"),
                        ("Order frequency", "c360-kpi-avg-freq"),
                        ("Repeat rate", "c360-kpi-repeat-rate"),
                    ]
                ),
                "c360-kpi-loading",
            ),
            html.Div(
                [
                    chart_panel(
                        "Customer segments",
                        "c360-rfm-segment-graph",
                        "c360-rfm-loading",
                        "span-8",
                    ),
                    chart_panel(
                        "Customer spend distribution",
                        "c360-spend-dist-graph",
                        "c360-spend-loading",
                        "span-4",
                    ),
                    panel(
                        "High-value customers",
                        loading(
                            html.Div(id="c360-top-customers-table-container"),
                            "c360-table-loading",
                        ),
                        "span-8",
                    ),
                    chart_panel(
                        "Active customer trend",
                        "c360-cust-trend-graph",
                        "c360-trend-loading",
                        "span-4",
                    ),
                ],
                className="dashboard-grid",
            ),
        ],
        className="dashboard-container",
    )


# --- ASYNC FILTER BAR POPULATION ON LOAD ---
@callback(
    Output("c360-filter-bar-container", "children"), Input("c360-page-loaded", "id")
)
def populate_c360_filter_bar(_):
    df_merged = get_prepared_dataset()
    return create_filter_bar(
        df_merged,
        date_picker_id="c360-date-picker",
        category_dropdown_id="c360-category-dropdown",
        country_dropdown_id="c360-country-dropdown",
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
    prevent_initial_call=True,
)
def sync_c360_filters_to_store(start_date, end_date, category, country):
    return {
        "start_date": start_date,
        "end_date": end_date,
        "category": category,
        "country": country,
    }


# --- KPI Callback ---
@callback(
    [
        Output("c360-kpi-active-cust-value", "children"),
        Output("c360-kpi-avg-spend-value", "children"),
        Output("c360-kpi-avg-freq-value", "children"),
        Output("c360-kpi-repeat-rate-value", "children"),
        Output("c360-kpi-active-cust-badge", "children"),
        Output("c360-kpi-avg-spend-badge", "children"),
        Output("c360-kpi-avg-freq-badge", "children"),
        Output("c360-kpi-repeat-rate-badge", "children"),
        Output("c360-kpi-active-cust-tooltip", "children"),
        Output("c360-kpi-avg-spend-tooltip", "children"),
        Output("c360-kpi-avg-freq-tooltip", "children"),
        Output("c360-kpi-repeat-rate-tooltip", "children"),
    ],
    Input("global-filter-store", "data"),
)
def update_customer_kpis(filter_data):
    empty_badge = dbc.Badge("N/A", color="secondary", className="small")

    if not filter_data:
        return (
            "0",
            "$0",
            "0.00",
            "0%",
            empty_badge,
            empty_badge,
            empty_badge,
            empty_badge,
            "",
            "",
            "",
            "",
        )

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    if not start_date or not end_date:
        return (
            "0",
            "$0",
            "0.00",
            "0%",
            empty_badge,
            empty_badge,
            empty_badge,
            empty_badge,
            "",
            "",
            "",
            "",
        )

    df_merged = get_prepared_dataset()

    curr_start = pd.to_datetime(start_date)
    curr_end = pd.to_datetime(end_date)
    date_diff = curr_end - curr_start

    prev_end = curr_start - pd.Timedelta(days=1)
    prev_start = prev_end - date_diff

    curr_df = filter_dataframe(
        df_merged, curr_start, curr_end, selected_category, selected_country
    )
    prev_df = filter_dataframe(
        df_merged, prev_start, prev_end, selected_category, selected_country
    )

    if curr_df.empty:
        return (
            "0",
            "$0",
            "0.00",
            "0%",
            empty_badge,
            empty_badge,
            empty_badge,
            empty_badge,
            "No data",
            "No data",
            "No data",
            "No data",
        )

    curr_summary = (
        curr_df.groupby("customer_key")
        .agg(
            total_spend=("gross_sales_amount", "sum"),
            total_orders=("order_number", "nunique"),
            total_units=("quantity", "sum"),
        )
        .reset_index()
    )

    curr_cust = len(curr_summary)
    curr_spend = curr_summary["total_spend"].sum() / curr_cust if curr_cust > 0 else 0
    curr_freq = curr_summary["total_orders"].sum() / curr_cust if curr_cust > 0 else 0
    curr_repeat_cnt = (curr_summary["total_orders"] > 1).sum()
    curr_repeat_rate = (curr_repeat_cnt / curr_cust * 100) if curr_cust > 0 else 0

    if not prev_df.empty:
        prev_summary = (
            prev_df.groupby("customer_key")
            .agg(
                total_spend=("gross_sales_amount", "sum"),
                total_orders=("order_number", "nunique"),
            )
            .reset_index()
        )

        prev_cust = len(prev_summary)
        prev_spend = (
            prev_summary["total_spend"].sum() / prev_cust if prev_cust > 0 else 0
        )
        prev_freq = (
            prev_summary["total_orders"].sum() / prev_cust if prev_cust > 0 else 0
        )
        prev_repeat_cnt = (prev_summary["total_orders"] > 1).sum()
        prev_repeat_rate = (prev_repeat_cnt / prev_cust * 100) if prev_cust > 0 else 0
    else:
        prev_cust = prev_spend = prev_freq = prev_repeat_rate = 0

    badge_cust = create_trend_badge(curr_cust, prev_cust)
    badge_spend = create_trend_badge(curr_spend, prev_spend)
    badge_freq = create_trend_badge(curr_freq, prev_freq)
    badge_repeat = create_trend_badge(curr_repeat_rate, prev_repeat_rate)

    single_order_cust = curr_cust - curr_repeat_cnt
    max_spend = curr_summary["total_spend"].max() if not curr_summary.empty else 0
    median_spend = curr_summary["total_spend"].median() if not curr_summary.empty else 0

    tt_cust = [
        html.Div(f"• Single-Order Cust: {single_order_cust:,}", className="text-start"),
        html.Div(f"• Repeat Cust: {curr_repeat_cnt:,}", className="text-start"),
    ]
    tt_spend = [
        html.Div(f"• Max Spend: ${max_spend:,.0f}", className="text-start"),
        html.Div(f"• Median Spend: ${median_spend:,.0f}", className="text-start"),
    ]
    tt_freq = [
        html.Div(
            f"• Total Orders: {curr_summary['total_orders'].sum():,}",
            className="text-start",
        ),
        html.Div(
            f"• Units/Cust: {(curr_summary['total_units'].sum()/curr_cust):,.1f}",
            className="text-start",
        ),
    ]
    tt_repeat = [
        html.Div(f"• Repeat Count: {curr_repeat_cnt:,}", className="text-start"),
        html.Div(f"• Single Count: {single_order_cust:,}", className="text-start"),
    ]

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
    Output("c360-rfm-segment-graph", "figure"), Input("global-filter-store", "data")
)
def update_rfm_segments(filter_data):
    if not filter_data:
        return style_figure(px.bar(title="No Data"))

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    df_merged = get_prepared_dataset()
    filtered_df = filter_dataframe(
        df_merged, start_date, end_date, selected_category, selected_country
    )

    if filtered_df.empty:
        return style_figure(px.bar(title="No Data"))

    max_ref_date = pd.to_datetime(end_date)
    filtered_df["order_date"] = pd.to_datetime(filtered_df["order_date"])

    rfm = (
        filtered_df.groupby("customer_key")
        .agg(
            recency=("order_date", lambda x: (max_ref_date - x.max()).days),
            frequency=("order_number", "nunique"),
            monetary=("gross_sales_amount", "sum"),
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
        "Champions": COLORS["success"],
        "Loyal Customers": COLORS["accent"],
        "Promising / Recent": COLORS["warning"],
        "Hibernating / Lost": COLORS["danger"],
    }

    fig = px.bar(
        seg_counts,
        x="Customer Count",
        y="Segment",
        orientation="h",
        color="Segment",
        color_discrete_map=color_map,
    )

    fig.update_traces(
        hovertemplate="<b>Segment:</b> %{y}<br><b>Customers:</b> %{x:,}<extra></extra>"
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            showgrid=True,
            gridcolor=COLORS["border"],
            tickfont=dict(color=COLORS["muted"]),
        ),
        yaxis=dict(showgrid=False, tickfont=dict(color=COLORS["muted"])),
        showlegend=False,
        height=320,
    )

    return style_figure(fig)


# --- Visual 2: Spend Distribution ---
@callback(
    Output("c360-spend-dist-graph", "figure"), Input("global-filter-store", "data")
)
def update_spend_distribution(filter_data):
    if not filter_data:
        return style_figure(px.histogram(title="No Data"))

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    df_merged = get_prepared_dataset()
    filtered_df = filter_dataframe(
        df_merged, start_date, end_date, selected_category, selected_country
    )

    if filtered_df.empty:
        return style_figure(px.histogram(title="No Data"))

    cust_spend = (
        filtered_df.groupby("customer_key")["gross_sales_amount"].sum().reset_index()
    )

    fig = px.histogram(
        cust_spend,
        x="gross_sales_amount",
        nbins=30,
        labels={
            "gross_sales_amount": "Total Customer Spend ($)",
            "count": "Customer Count",
        },
        color_discrete_sequence=[COLORS["success"]],
    )

    fig.update_traces(
        hovertemplate="<b>Spend Range:</b> %{x}<br><b>Customers:</b> %{y}<extra></extra>"
    )

    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(
            showgrid=True,
            gridcolor=COLORS["border"],
            tickfont=dict(color=COLORS["muted"]),
        ),
        xaxis=dict(
            showgrid=False, tickprefix="$", tickfont=dict(color=COLORS["muted"])
        ),
        height=320,
    )

    return style_figure(fig)


# --- Visual 3: Top High-Value Customers Table ---
@callback(
    Output("c360-top-customers-table-container", "children"),
    Input("global-filter-store", "data"),
)
def update_top_customers_table(filter_data):
    if not filter_data:
        return html.Div(
            "No transactions found for selection.",
            className="text-muted p-3 text-center",
        )

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    df_merged = get_prepared_dataset()
    filtered_df = filter_dataframe(
        df_merged, start_date, end_date, selected_category, selected_country
    )

    if filtered_df.empty:
        return html.Div(
            "No transactions found for selection.",
            className="text-muted p-3 text-center",
        )

    top_cust = (
        filtered_df.groupby(["first_name", "last_name", "country"])
        .agg(
            total_spend=("gross_sales_amount", "sum"),
            total_orders=("order_number", "nunique"),
        )
        .reset_index()
        .sort_values(by="total_spend", ascending=False)
        .head(10)
    )

    top_cust["customer_name"] = (
        top_cust["first_name"].fillna("") + " " + top_cust["last_name"].fillna("")
    )

    column_defs = [
        {"field": "customer_name", "headerName": "Customer"},
        {"field": "country", "headerName": "Country"},
        {"field": "total_orders", "headerName": "Orders", "type": "rightAligned"},
        {
            "field": "total_spend",
            "headerName": "Total Spend",
            "type": "rightAligned",
            "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"},
        },
    ]

    grid = create_grid(column_defs, top_cust.to_dict("records"))

    return grid


# --- Visual 4: Active Customer Trend ---
@callback(
    Output("c360-cust-trend-graph", "figure"), Input("global-filter-store", "data")
)
def update_customer_trend(filter_data):
    if not filter_data:
        return style_figure(px.line(title="No Data"))

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    df_merged = get_prepared_dataset()
    filtered_df = filter_dataframe(
        df_merged, start_date, end_date, selected_category, selected_country
    )

    if filtered_df.empty:
        return style_figure(px.line(title="No Data"))

    df_trend = filtered_df.copy()
    df_trend["year_month"] = (
        pd.to_datetime(df_trend["order_date"]).dt.to_period("M").dt.to_timestamp()
    )

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
        color_discrete_sequence=[COLORS["accent"]],
    )

    fig.update_traces(
        mode="lines+markers",
        line=dict(width=3, color=COLORS["accent"]),
        marker=dict(size=6, color=COLORS["accent"]),
        hovertemplate="<b>Date:</b> %{x|%b %Y}<br><b>Active Cust:</b> %{y:,}<extra></extra>",
    )

    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(
            showgrid=True,
            gridcolor=COLORS["border"],
            tickfont=dict(color=COLORS["muted"]),
        ),
        xaxis=dict(showgrid=False, tickfont=dict(color=COLORS["muted"])),
        height=320,
    )

    return style_figure(fig)

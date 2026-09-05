import dash
from dash import html, dcc, callback, Input, Output, dash_table
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
from data_loader import load_and_prep_data

# Register Page
dash.register_page(__name__, path="/customers", name="Customer 360")

# Fetch prepped data
df_merged, min_data_date, max_data_date, category_options, country_options = load_and_prep_data()

layout = html.Div(
    className="dashboard-container py-3",
    children=[
        dbc.Container(
            [
                # Row 1: Filter Control Bar
                dbc.Row(
                    dbc.Col(
                        html.Div(
                            [
                                dbc.Row(
                                    [
                                        dbc.Col(
                                            [
                                                html.Label("Date Range", className="fw-bold text-muted small mb-0"),
                                                dcc.DatePickerRange(
                                                    id="c360-date-picker",
                                                    min_date_allowed=min_data_date,
                                                    max_date_allowed=max_data_date,
                                                    start_date=min_data_date,
                                                    end_date=max_data_date,
                                                    display_format="YYYY-MM-DD",
                                                    className="w-100",
                                                ),
                                            ],
                                            width=12, md=4
                                        ),
                                        dbc.Col(
                                            [
                                                html.Label("Product Category", className="fw-bold text-muted small mb-0"),
                                                dcc.Dropdown(
                                                    id="c360-category-dropdown",
                                                    options=category_options,
                                                    value="ALL",
                                                    clearable=False,
                                                ),
                                            ],
                                            width=12, md=4
                                        ),
                                        dbc.Col(
                                            [
                                                html.Label("Region", className="fw-bold text-muted small mb-0"),
                                                dcc.Dropdown(
                                                    id="c360-country-dropdown",
                                                    options=country_options,
                                                    value="ALL",
                                                    clearable=False,
                                                ),
                                            ],
                                            width=12, md=4
                                        ),
                                    ],
                                    className="g-2 align-items-center"
                                )
                            ],
                            className="bg-white p-2 rounded shadow-sm border mb-3"
                        ),
                        width=12
                    ),
                    className="sticky-filter-bar"
                ),

                # Row 2: KPI Cards
                dbc.Row(
                    [
                        dbc.Col(
                            html.Div(
                                [
                                    html.H6("ACTIVE CUSTOMERS", className="text-muted fw-bold mb-0 small"),
                                    html.H3(id="c360-kpi-active-cust", className="text-dark fw-bold mb-0"),
                                    dbc.Tooltip(id="c360-tooltip-cust", target="c360-card-cust", placement="top")
                                ],
                                id="c360-card-cust",
                                className="kpi-card p-2 border-start border-4 border-info bg-white rounded shadow-sm cursor-pointer"
                            ),
                            width=3
                        ),
                        dbc.Col(
                            html.Div(
                                [
                                    html.H6("AVG SPEND / CUST", className="text-muted fw-bold mb-0 small"),
                                    html.H3(id="c360-kpi-avg-spend", className="text-dark fw-bold mb-0"),
                                    dbc.Tooltip(id="c360-tooltip-spend", target="c360-card-spend", placement="top")
                                ],
                                id="c360-card-spend",
                                className="kpi-card p-2 border-start border-4 border-success bg-white rounded shadow-sm cursor-pointer"
                            ),
                            width=3
                        ),
                        dbc.Col(
                            html.Div(
                                [
                                    html.H6("AVG ORDERS / CUST", className="text-muted fw-bold mb-0 small"),
                                    html.H3(id="c360-kpi-avg-freq", className="text-dark fw-bold mb-0"),
                                    dbc.Tooltip(id="c360-tooltip-freq", target="c360-card-freq", placement="top")
                                ],
                                id="c360-card-freq",
                                className="kpi-card p-2 border-start border-4 border-warning bg-white rounded shadow-sm cursor-pointer"
                            ),
                            width=3
                        ),
                        dbc.Col(
                            html.Div(
                                [
                                    html.H6("REPEAT RATE", className="text-muted fw-bold mb-0 small"),
                                    html.H3(id="c360-kpi-repeat-rate", className="text-dark fw-bold mb-0"),
                                    dbc.Tooltip(id="c360-tooltip-repeat", target="c360-card-repeat", placement="top")
                                ],
                                id="c360-card-repeat",
                                className="kpi-card p-2 border-start border-4 border-primary bg-white rounded shadow-sm cursor-pointer"
                            ),
                            width=3
                        ),
                    ],
                    className="g-2 mb-3"
                ),

                # Row 3: Visuals Row 1
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Customer Spend Distribution (CLV)", className="fw-bold text-dark mb-2"),
                                        dcc.Graph(id="c360-spend-dist-graph", config={"displayModeBar": False})
                                    ]
                                ),
                                className="shadow-sm border-0 mb-3"
                            ),
                            width=12, lg=7
                        ),
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Top High-Value Customers", className="fw-bold text-dark mb-2"),
                                        html.Div(id="c360-top-customers-table-container")
                                    ]
                                ),
                                className="shadow-sm border-0 mb-3"
                            ),
                            width=12, lg=5
                        ),
                    ]
                ),

                # Row 4: Visuals Row 2 (NEW)
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Active Customer Trend", className="fw-bold text-dark mb-2"),
                                        dcc.Graph(id="c360-cust-trend-graph", config={"displayModeBar": False})
                                    ]
                                ),
                                className="shadow-sm border-0 mb-3"
                            ),
                            width=12, lg=7
                        ),
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Customer Concentration by Region", className="fw-bold text-dark mb-2"),
                                        dcc.Graph(id="c360-cust-geo-graph", config={"displayModeBar": False})
                                    ]
                                ),
                                className="shadow-sm border-0 mb-3"
                            ),
                            width=12, lg=5
                        )
                    ]
                )
            ],
            fluid=False
        )
    ]
)

def filter_dataframe(df, start_date, end_date, selected_category, selected_country):
    if not start_date or not end_date:
        return df.iloc[0:0]

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)

    mask = (df["order_date"] >= start_dt) & (df["order_date"] <= end_dt)

    if selected_category and selected_category != "ALL":
        mask = mask & (df["category"] == selected_category)

    if selected_country and selected_country != "ALL":
        mask = mask & (df["country"] == selected_country)

    return df.loc[mask]

@callback(
    [
        Output("c360-kpi-active-cust", "children"),
        Output("c360-kpi-avg-spend", "children"),
        Output("c360-kpi-avg-freq", "children"),
        Output("c360-kpi-repeat-rate", "children"),
        Output("c360-tooltip-cust", "children"),
        Output("c360-tooltip-spend", "children"),
        Output("c360-tooltip-freq", "children"),
        Output("c360-tooltip-repeat", "children"),
    ],
    [
        Input("c360-date-picker", "start_date"),
        Input("c360-date-picker", "end_date"),
        Input("c360-category-dropdown", "value"),
        Input("c360-country-dropdown", "value"),
    ],
)
def update_customer_kpis(start_date, end_date, selected_category, selected_country):
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

    if filtered_df.empty:
        return "0", "$0", "0.00", "0%", "No data", "No data", "No data", "No data"

    # Per-customer metrics aggregation
    cust_summary = (
        filtered_df.groupby("customer_key")
        .agg(
            total_spend=("gross_sales_amount", "sum"),
            total_orders=("order_number", "nunique"),
            total_units=("quantity", "sum")
        )
        .reset_index()
    )

    total_active_cust = len(cust_summary)
    total_revenue = cust_summary["total_spend"].sum()
    total_orders = cust_summary["total_orders"].sum()

    avg_spend = total_revenue / total_active_cust if total_active_cust > 0 else 0
    avg_freq = total_orders / total_active_cust if total_active_cust > 0 else 0

    repeat_customers = (cust_summary["total_orders"] > 1).sum()
    repeat_rate = (repeat_customers / total_active_cust * 100) if total_active_cust > 0 else 0

    # Tooltip contents
    single_order_cust = total_active_cust - repeat_customers
    max_spend = cust_summary["total_spend"].max() if not cust_summary.empty else 0
    median_spend = cust_summary["total_spend"].median() if not cust_summary.empty else 0

    tt_cust = [html.Div(f"• Single-Order Cust: {single_order_cust:,}"), html.Div(f"• Repeat Cust: {repeat_customers:,}")]
    tt_spend = [html.Div(f"• Max Spend: ${max_spend:,.0f}"), html.Div(f"• Median Spend: ${median_spend:,.0f}")]
    tt_freq = [html.Div(f"• Total Orders: {total_orders:,}"), html.Div(f"• Units/Cust: {(cust_summary['total_units'].sum()/total_active_cust):,.1f}")]
    tt_repeat = [html.Div(f"• Repeat Count: {repeat_customers:,}"), html.Div(f"• Single Count: {single_order_cust:,}")]

    return (
        f"{total_active_cust:,}",
        f"${avg_spend:,.0f}",
        f"{avg_freq:,.2f}",
        f"{repeat_rate:.1f}%",
        tt_cust,
        tt_spend,
        tt_freq,
        tt_repeat,
    )

# --- Visual 1: Spend Distribution ---
@callback(
    Output("c360-spend-dist-graph", "figure"),
    [
        Input("c360-date-picker", "start_date"),
        Input("c360-date-picker", "end_date"),
        Input("c360-category-dropdown", "value"),
        Input("c360-country-dropdown", "value"),
    ],
)
def update_spend_distribution(start_date, end_date, selected_category, selected_country):
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

    if filtered_df.empty:
        return px.histogram(title="No Data")

    cust_spend = filtered_df.groupby("customer_key")["gross_sales_amount"].sum().reset_index()

    fig = px.histogram(
        cust_spend,
        x="gross_sales_amount",
        nbins=30,
        labels={"gross_sales_amount": "Total Customer Spend ($)", "count": "Customer Count"},
        color_discrete_sequence=["#2ecc71"]
    )

    fig.update_traces(hovertemplate="<b>Spend Range:</b> %{x}<br><b>Customers:</b> %{y}<extra></extra>")
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
        xaxis=dict(showgrid=False, tickprefix="$"),
        height=320
    )

    return fig


# --- Visual 2: Top High-Value Customers Table ---
@callback(
    Output("c360-top-customers-table-container", "children"),
    [
        Input("c360-date-picker", "start_date"),
        Input("c360-date-picker", "end_date"),
        Input("c360-category-dropdown", "value"),
        Input("c360-country-dropdown", "value"),
    ],
)
def update_top_customers_table(start_date, end_date, selected_category, selected_country):
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

    table = dash_table.DataTable(
        data=top_cust.to_dict("records"),
        columns=[
            {"name": "Customer", "id": "customer_name"},
            {"name": "Country", "id": "country"},
            {"name": "Orders", "id": "total_orders", "type": "numeric"},
            {"name": "Total Spend", "id": "total_spend", "type": "numeric", "format": {"specifier": "$,.0f"}},
        ],
        page_size=10,

        style_table={"overflowX": "auto", 'height':'320px'},
        style_header={"backgroundColor": "#f8f9fa", "fontWeight": "bold", "color": "#2c3e50"},
        style_cell={"padding": "8px 12px", "fontSize": "0.85rem", "textAlign": "left"},
        style_cell_conditional=[
            {"if": {"column_id": "total_orders"}, "textAlign": "right"},
            {"if": {"column_id": "total_spend"}, "textAlign": "right"},
        ],
        style_header_conditional=[
            {"if": {"column_id": "total_orders"}, "textAlign": "right"},
            {"if": {"column_id": "total_spend"}, "textAlign": "right"},
        ]
    )

    return table

# --- Visual 3: Active Customer Trend ---
@callback(
    Output("c360-cust-trend-graph", "figure"),
    [
        Input("c360-date-picker", "start_date"),
        Input("c360-date-picker", "end_date"),
        Input("c360-category-dropdown", "value"),
        Input("c360-country-dropdown", "value"),
    ],
)
def update_customer_trend(start_date, end_date, selected_category, selected_country):
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

    if filtered_df.empty:
        return px.line(title="No Data")

    # Group by Month & Year to get distinct active customers
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
        color_discrete_sequence=["#3498db"]
    )

    fig.update_traces(hovertemplate="<b>Date:</b> %{x|%b %Y}<br><b>Active Cust:</b> %{y:,}<extra></extra>")
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
        xaxis=dict(showgrid=False),
        height=320
    )

    return fig


# --- Visual 4: Geographic Customer Concentration ---
@callback(
    Output("c360-cust-geo-graph", "figure"),
    [
        Input("c360-date-picker", "start_date"),
        Input("c360-date-picker", "end_date"),
        Input("c360-category-dropdown", "value"),
        Input("c360-country-dropdown", "value"),
    ],
)
def update_customer_geo(start_date, end_date, selected_category, selected_country):
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

    if filtered_df.empty:
        return px.bar(title="No Data")

    geo_summary = (
        filtered_df.groupby("country")["customer_key"]
        .nunique()
        .reset_index(name="active_customers")
        .sort_values(by="active_customers", ascending=True)
        .tail(10)
    )

    fig = px.bar(
        geo_summary,
        x="active_customers",
        y="country",
        orientation="h",
        labels={"active_customers": "Active Customers", "country": "Country"},
        color_discrete_sequence=["#9b59b6"]
    )

    fig.update_traces(hovertemplate="<b>Country:</b> %{y}<br><b>Active Cust:</b> %{x:,}<extra></extra>")
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
        yaxis=dict(showgrid=False),
        height=320
    )

    return fig
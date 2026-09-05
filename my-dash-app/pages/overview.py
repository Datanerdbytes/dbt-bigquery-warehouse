import dash
import pandas as pd
import plotly.express as px
from dash import Dash, html, dcc, callback, Input, Output, dash_table, State, callback_context
import dash_bootstrap_components as dbc
from data_loader import load_and_prep_data

# Unpack data and configuration variables
df_merged, min_data_date, max_data_date, category_options, country_options = load_and_prep_data()

dash.register_page(__name__, path="/", name="Product Overview")

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
                                                    id="date-picker-range",
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
                                                    id="category-dropdown",
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
                                                    id="country-dropdown",
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
                                    html.H6("TOTAL SALES", className="text-muted fw-bold mb-0 small"),
                                    html.H3(id="kpi-sales-value", className="text-dark fw-bold mb-0"),
                                    dbc.Tooltip(id="kpi-sales-tooltip", target="kpi-sales-card", placement="top")
                                ],
                                id="kpi-sales-card",
                                className="kpi-card p-2 border-start border-4 border-info bg-white rounded shadow-sm cursor-pointer"
                            ),
                            width=3
                        ),
                        dbc.Col(
                            html.Div(
                                [
                                    html.H6("TOTAL ORDERS", className="text-muted fw-bold mb-0 small"),
                                    html.H3(id="kpi-orders-value", className="text-dark fw-bold mb-0"),
                                    dbc.Tooltip(id="kpi-orders-tooltip", target="kpi-orders-card", placement="top")
                                ],
                                id="kpi-orders-card",
                                className="kpi-card p-2 border-start border-4 border-success bg-white rounded shadow-sm cursor-pointer"
                            ),
                            width=3
                        ),
                        dbc.Col(
                            html.Div(
                                [
                                    html.H6("TOTAL QUANTITY", className="text-muted fw-bold mb-0 small"),
                                    html.H3(id="kpi-quantity-value", className="text-dark fw-bold mb-0"),
                                    dbc.Tooltip(id="kpi-quantity-tooltip", target="kpi-quantity-card", placement="top")
                                ],
                                id="kpi-quantity-card",
                                className="kpi-card p-2 border-start border-4 border-warning bg-white rounded shadow-sm cursor-pointer"
                            ),
                            width=3
                        ),
                        dbc.Col(
                            html.Div(
                                [
                                    html.H6("TOTAL CUSTOMERS", className="text-muted fw-bold mb-0 small"),
                                    html.H3(id="kpi-customers-value", className="text-dark fw-bold mb-0"),
                                    dbc.Tooltip(id="kpi-customers-tooltip", target="kpi-customers-card", placement="top")
                                ],
                                id="kpi-customers-card",
                                className="kpi-card p-2 border-start border-4 border-primary bg-white rounded shadow-sm cursor-pointer"
                            ),
                            width=3
                        )
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
                                        html.H5("Sales Revenue Performance", className="fw-bold text-dark mb-2"),
                                        dcc.Graph(id="sales-trend-graph", config={"displayModeBar": False})
                                    ],
                                    className="p-3"
                                ),
                                className="shadow-sm border-0 mb-3"
                            ),
                            width=12, lg=7
                        ),
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Revenue by Category", className="fw-bold text-dark mb-2"),
                                        dcc.Graph(id="category-pie-graph", config={"displayModeBar": False})
                                    ],
                                    className="p-3"
                                ),
                                className="shadow-sm border-0 mb-3"
                            ),
                            width=12, lg=5
                        )
                    ]
                ),

                # Row 4: Visuals Row 2
                dbc.Row(
                    [
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Top 10 Products by Revenue", className="fw-bold text-dark mb-2"),
                                        dcc.Graph(id="top-products-graph", config={"displayModeBar": False})
                                    ],
                                    className="p-3"
                                ),
                                className="shadow-sm border-0 mb-3"
                            ),
                            width=12, lg=6
                        ),
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Regional Revenue Breakdown", className="fw-bold text-dark mb-2"),
                                        dcc.Graph(id="regional-sales-graph", config={"displayModeBar": False})
                                    ],
                                    className="p-3"
                                ),
                                className="shadow-sm border-0 mb-3"
                            ),
                            width=12, lg=6
                        )
                    ]
                )
            ],
            fluid=False
        ),

        # Modal
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle(id="modal-product-title", className="fw-bold")),
                dbc.ModalBody(
                    [
                        html.Div(id="modal-product-kpis", className="mb-3"),
                        html.H6("Recent Transactions", className="fw-bold text-muted mb-2"),
                        html.Div(id="modal-product-table-container")
                    ]
                ),
                dbc.ModalFooter(
                    dbc.Button("Close", id="close-modal-btn", className="ms-auto", color="secondary")
                ),
            ],
            id="product-detail-modal",
            size="xl",
            is_open=False,
            centered=True
        )
    ]
)


def filter_dataframe(df, start_date, end_date, selected_category, selected_country):
    if not start_date or not end_date:
        return df.iloc[0:0]

    # Convert string inputs to Pandas Datetime with full end-of-day coverage
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)

    mask = (df["order_date"] >= start_dt) & (df["order_date"] <= end_dt)

    if selected_category and selected_category != "ALL":
        mask = mask & (df["category"] == selected_category)

    if selected_country and selected_country != "ALL":
        mask = mask & (df["country"] == selected_country)

    return df.loc[mask]


# --- KPI CALLBACK ---
@callback(
    [
        Output("kpi-sales-value", "children"),
        Output("kpi-orders-value", "children"),
        Output("kpi-quantity-value", "children"),
        Output("kpi-customers-value", "children"),
        Output("kpi-sales-tooltip", "children"),
        Output("kpi-orders-tooltip", "children"),
        Output("kpi-quantity-tooltip", "children"),
        Output("kpi-customers-tooltip", "children"),
    ],
    [
        Input("date-picker-range", "start_date"),
        Input("date-picker-range", "end_date"),
        Input("category-dropdown", "value"),
        Input("country-dropdown", "value")
    ],
)
def update_all_kpis(start_date, end_date, selected_category, selected_country):
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

    if filtered_df.empty:
        return "$0", "0", "0", "0", "No data available"

    total_sales = filtered_df["gross_sales_amount"].sum()
    total_orders = filtered_df["order_number"].nunique()
    total_quantity = filtered_df["quantity"].sum()
    total_customers = filtered_df["customer_key"].nunique()

    # --- Sales Tooltip Metrics ---
    aov = total_sales / total_orders if total_orders > 0 else 0
    active_days = filtered_df["order_date"].dt.date.nunique()
    daily_avg_sales = total_sales / active_days if active_days > 0 else 0

    sales_tooltip_content = [
        html.Div(f"• Avg Order Value (AOV): ${aov:,.2f}", className="text-start"),
        html.Div(f"• Daily Avg Revenue: ${daily_avg_sales:,.0f}", className="text-start")
    ]

    # --- Orders Tooltip Metrics ---
    daily_avg_orders = total_orders / active_days if active_days > 0 else 0
    items_per_order = total_quantity / total_orders if total_orders > 0 else 0

    orders_tooltip_content = [
        html.Div(f"• Daily Avg Orders: {daily_avg_orders:,.1f}", className="text-start"),
        html.Div(f"• Units Per Order: {items_per_order:,.1f}", className="text-start")
    ]

    # --- Quantity Tooltip Metrics ---
    daily_avg_qty = total_quantity / active_days if active_days > 0 else 0
    avg_unit_price = total_sales / total_quantity if total_quantity > 0 else 0

    quantity_tooltip_content = [
        html.Div(f"• Daily Avg Units: {daily_avg_qty:,.1f}", className="text-start"),
        html.Div(f"• Effective Unit Price: ${avg_unit_price:,.2f}", className="text-start")
    ]

    # --- Customers Tooltip Metrics ---
    rev_per_customer = total_sales / total_customers if total_customers > 0 else 0
    orders_per_customer = total_orders / total_customers if total_customers > 0 else 0

    customers_tooltip_content = [
        html.Div(f"• Revenue / Customer: ${rev_per_customer:,.2f}", className="text-start"),
        html.Div(f"• Orders / Customer: {orders_per_customer:,.2f}", className="text-start")
    ]

    return (
        f"${total_sales:,.0f}",
        f"{total_orders:,}",
        f"{total_quantity:,}",
        f"{total_customers:,}",
        sales_tooltip_content,
        orders_tooltip_content,
        quantity_tooltip_content,
        customers_tooltip_content,
    )


# --- CHART 1 CALLBACK: Sales Revenue Trend ---
@callback(
    Output("sales-trend-graph", "figure"),
    [
        Input("date-picker-range", "start_date"),
        Input("date-picker-range", "end_date"),
        Input("category-dropdown", "value"),
        Input("country-dropdown", "value")
    ],
)
def update_sales_trend(start_date, end_date, selected_category, selected_country):
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

    if filtered_df.empty:
        return px.area(title="No data for selected period")

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    resample_freq = "D" if (end_dt - start_dt).days <= 60 else "ME"

    trend_df = (
        filtered_df.set_index("order_date")
        .resample(resample_freq)["gross_sales_amount"]
        .sum()
        .reset_index()
    )

    fig = px.area(
        trend_df,
        x="order_date",
        y="gross_sales_amount",
        labels={"order_date": "", "gross_sales_amount": "Revenue ($)"},
    )

    fig.update_traces(
        line_color="#2ecc71",
        fillcolor="rgba(46, 204, 113, 0.15)",
        hovertemplate="<b>Date:</b> %{x|%b %d, %Y}<br><b>Revenue:</b> $%{y:,.0f}<extra></extra>"
    )

    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#f0f0f0", tickprefix="$"),
        height=260
    )

    return fig


# --- CHART 2 CALLBACK: Revenue by Product Category ---
@callback(
    Output("category-pie-graph", "figure"),
    [
        Input("date-picker-range", "start_date"),
        Input("date-picker-range", "end_date"),
        Input("category-dropdown", "value"),
        Input("country-dropdown", "value")
    ],
)
def update_category_pie(start_date, end_date, selected_category, selected_country):
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

    if filtered_df.empty:
        return px.pie()

    cat_df = (
        filtered_df.groupby("category")["gross_sales_amount"]
        .sum()
        .reset_index()
    )

    cat_df["category"] = cat_df["category"].astype(str).str.title()

    fig = px.pie(
        cat_df,
        names="category",
        values="gross_sales_amount",
        hole=0.55,
        color_discrete_sequence=["#2ecc71", "#3498db", "#9b59b6", "#f39c12", "#e74c3c"]
    )

    fig.update_traces(
        textinfo="percent+label",
        hovertemplate="<b>Category:</b> %{label}<br><b>Revenue:</b> $%{value:,.0f} (%{percent})<extra></extra>",
        marker=dict(line=dict(color="#ffffff", width=2))
    )

    fig.update_layout(
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=260
    )

    return fig


# --- CHART 3 CALLBACK: Top 10 Products by Revenue ---
@callback(
    Output("top-products-graph", "figure"),
    [
        Input("date-picker-range", "start_date"),
        Input("date-picker-range", "end_date"),
        Input("category-dropdown", "value"),
        Input("country-dropdown", "value"),
    ],
)
def update_top_products(start_date, end_date, selected_category, selected_country):
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

    if filtered_df.empty:
        return px.bar()

    top_products_df = (
        filtered_df.groupby("product_name")["gross_sales_amount"]
        .sum()
        .reset_index()
        .sort_values(by="gross_sales_amount", ascending=True)
        .tail(10)
    )

    fig = px.bar(
        top_products_df,
        x="gross_sales_amount",
        y="product_name",
        orientation="h",
        labels={"gross_sales_amount": "Revenue ($)", "product_name": ""},
        text_auto="$,.0f",
    )

    fig.update_traces(
        marker_color="#3498db",
        hovertemplate="<b>Product:</b> %{y}<br><b>Revenue:</b> $%{x:,.0f}<extra></extra>",
        textposition="outside",
        cliponaxis=False,
    )

    raw_max = top_products_df["gross_sales_amount"].max() if not top_products_df.empty else 0
    max_val = float(raw_max) if raw_max is not None else 0.0

    fig.update_layout(
        margin=dict(l=10, r=20, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=True, gridcolor="#f0f0f0", tickprefix="$"),
        yaxis=dict(showgrid=False),
        height=350,
    )

    fig.update_xaxes(range=[0, max_val * 1.15])

    return fig


# --- CHART 4 CALLBACK: Regional Revenue Breakdown ---
@callback(
    Output("regional-sales-graph", "figure"),
    [
        Input("date-picker-range", "start_date"),
        Input("date-picker-range", "end_date"),
        Input("category-dropdown", "value"),
        Input("country-dropdown", "value"),
    ],
)
def update_regional_sales(start_date, end_date, selected_category, selected_country):
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

    if filtered_df.empty:
        return px.bar()

    region_df = (
        filtered_df.groupby("country")["gross_sales_amount"]
        .sum()
        .reset_index()
        .sort_values(by="gross_sales_amount", ascending=False)
    )

    region_df["country"] = region_df["country"].astype(str).str.title()

    fig = px.bar(
        region_df,
        x="country",
        y="gross_sales_amount",
        labels={"gross_sales_amount": "Revenue ($)", "country": ""},
        text_auto="$,.0f"
    )

    fig.update_traces(
        marker_color="#9b59b6",
        hovertemplate="<b>Country:</b> %{x}<br><b>Revenue:</b> $%{y:,.0f}<extra></extra>",
        textposition="outside",
        cliponaxis=False
    )

    raw_max = region_df["gross_sales_amount"].max() if not region_df.empty else 0
    max_val = float(raw_max) if raw_max is not None else 0.0

    fig.update_layout(
        margin=dict(l=10, r=10, t=20, b=10), 
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#f0f0f0", tickprefix="$"),
        height=350
    )

    fig.update_yaxes(range=[0, max_val * 1.15])

    return fig


# --- MODAL CALLBACK ---
@callback(
    [
        Output("product-detail-modal", "is_open"),
        Output("modal-product-title", "children"),
        Output("modal-product-kpis", "children"),
        Output("modal-product-table-container", "children")
    ],
    [
        Input("top-products-graph", "clickData"),
        Input("close-modal-btn", "n_clicks")
    ],
    [
        State("date-picker-range", "start_date"),
        State("date-picker-range", "end_date"),
        State("category-dropdown", "value"),
        State("country-dropdown", "value")
    ],
    prevent_initial_call=True
)
def toggle_product_modal(clickData, close_clicks, start_date, end_date, selected_category, selected_country):
    ctx = callback_context
    if not ctx.triggered:
        return False, "", None, None

    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if trigger_id == "close-modal-btn":
        return False, "", None, None

    if trigger_id == "top-products-graph" and clickData:
        product_name = clickData["points"][0]["y"]

        # Reuse filter_dataframe and then narrow down to the target product
        filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)
        product_df = filtered_df.loc[filtered_df["product_name"] == product_name].copy()

        if product_df.empty:
            return True, f"Product Details: {product_name}", None, html.Div("No transactions found within the selected date range.", className="p-3 text-muted text-center fw-bold")

        total_rev = product_df["gross_sales_amount"].sum()
        total_qty = product_df["quantity"].sum()
        total_orders = product_df["order_number"].nunique()

        kpi_summary = dbc.Row([
            dbc.Col(html.Div([html.Small("Revenue", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"${total_rev:,.0f}", className="fs-5")]), width=4),
            dbc.Col(html.Div([html.Small("Units Sold", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"{total_qty:,}", className="fs-5")]), width=4),
            dbc.Col(html.Div([html.Small("Total Orders", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"{total_orders:,}", className="fs-5")]), width=4),
        ], className="bg-light p-3 rounded mb-3 text-center border")

        records_df = (
            product_df[["order_number", "order_date", "first_name", "last_name", "country", "quantity", "gross_sales_amount"]]
            .sort_values(by="order_date", ascending=False)
            .head(50)
        )
        records_df["customer_name"] = records_df["first_name"].fillna('') + " " + records_df["last_name"].fillna('')
        records_df["order_date"] = records_df["order_date"].dt.strftime("%Y-%m-%d")

        detail_table = dash_table.DataTable(
            data=records_df.to_dict("records"),
            columns=[
                {"name": "Order #", "id": "order_number"},
                {"name": "Date", "id": "order_date"},
                {"name": "Customer", "id": "customer_name"},
                {"name": "Country", "id": "country"},
                {"name": "Qty", "id": "quantity", "type": "numeric"},
                {"name": "Revenue ($)", "id": "gross_sales_amount", "type": "numeric", "format": {"specifier": "$,.0f"}},
            ],
            page_size=8,
            style_table={"overflowX": "auto"},
            style_header={"backgroundColor": "#f8f9fa", "fontWeight": "bold", "color": "#2c3e50", "textAlign": "left"},
            style_cell={"padding": "10px 14px", "fontSize": "0.85rem", "fontFamily": "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif", "textAlign": "left"},
            style_cell_conditional=[
                {"if": {"column_id": "quantity"}, "textAlign": "right"},
                {"if": {"column_id": "gross_sales_amount"}, "textAlign": "right"},
            ],
            style_header_conditional=[
                {"if": {"column_id": "quantity"}, "textAlign": "right"},
                {"if": {"column_id": "gross_sales_amount"}, "textAlign": "right"},
            ],
            style_data_conditional=[{"if": {"row_index": "odd"}, "backgroundColor": "#fcfcfc"}]
        )

        return True, f"Product Details: {product_name}", kpi_summary, detail_table

    return False, "", None, None
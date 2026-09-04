import os
from datetime import date
from dotenv import load_dotenv
from google.cloud import bigquery
import pandas as pd
import numpy as np
import plotly.express as px
from dash import Dash, html, dcc, callback, Input, Output, dash_table
import dash_bootstrap_components as dbc

load_dotenv()

key_file_path = os.environ.get("GCP_KEY_PATH")

client = bigquery.Client.from_service_account_json(
    key_file_path,
    project="quantum-echo-data-eng-prod"
)

query_sales = """
    SELECT 
        product_key, 
        customer_key,
        order_date, 
        order_number,
        quantity,
        gross_sales_amount, 
        unit_price 
    FROM `quantum-echo-data-eng-prod.gold.fct_sales`
"""

query_products = """
     SELECT 
        product_key,
        product_name, 
        category 
    FROM `quantum-echo-data-eng-prod.gold.dim_products`
"""

query_customers = """
     SELECT 
        customer_key,
        first_name, 
        last_name,
        country
    FROM `quantum-echo-data-eng-prod.gold.dim_customers`
"""

df_sales = client.query(query_sales).to_dataframe()
df_products = client.query(query_products).to_dataframe()
df_customers = client.query(query_customers).to_dataframe()

df_sales['order_date'] = pd.to_datetime(df_sales['order_date'])

# 1. Merge all three tables
df_merged = (
    df_sales
    .merge(df_products, on="product_key", how="left")
    .merge(df_customers, on="customer_key", how="left")  
)

# --- DYNAMIC Date Range OPTIONS SETUP ---
df_merged = df_merged[df_merged["order_date"].dt.year >= 2010].copy()

min_data_date = df_merged["order_date"].min().date()
max_data_date = df_merged["order_date"].max().date()

# --- DYNAMIC CATEGORY OPTIONS SETUP ---
# Extract unique categories, drop NaNs, and sort them
unique_categories = sorted(df_merged["category"].dropna().unique())

# Build the dropdown options list with an "All Categories" default option
category_options = [{"label": "All Categories", "value": "ALL"}] + [
    {"label": str(cat).title(), "value": cat} for cat in unique_categories
]

# --- DYNAMIC Regions OPTIONS SETUP ---
# 1. Extract unique countries using a distinct variable name
unique_countries = sorted(df_merged["country"].dropna().unique())

# 2. Build options dictionary list
country_options = [{"label": "All Countries", "value": "ALL"}] + [
    {"label": str(cntry).title(), "value": cntry} for cntry in unique_countries
]



# 2. Compute KPIs into a clean 1D Series
kpis = pd.Series({
    "total_sales":  df_merged["gross_sales_amount"].sum(),
    "total_orders": df_merged["order_number"].nunique(),
    "total_quantity": df_merged["quantity"].sum(),
    "total_customers": df_merged["customer_key"].nunique()
})


app = Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])

app.layout = html.Div(
    className="dashboard-container",
    children=[
        dbc.Container(
            [   # Row 1: Header Banner
                dbc.Row(
                    [   
                        dbc.Col(
                            [
                                html.Div(
                                    [
                                        html.H2(
                                            "Product 360 Executive Dashboard",
                                            className="fw-bold mb-0 text-white",
                                        ),
                                        html.P(
                                            "Comprehensive Performance, Health, and Customer Metrics",
                                            className="mb-0 text-white-50 small",
                                        )
                                    ],
                                    className="header-banner p-2 mb-2"
                                )
                            ],
                            width=12
                        )
                    ]
                ),

                # Row 2: Dedicated Filter Control Bar
                dbc.Row(
                    dbc.Col(
                        html.Div(
                            [
                                dbc.Row(
                                    [
                                        # Filter 1: Date Range
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
                                        # Filter 2: Product Category Dropdown
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
                                        # Filter 3: Region Selector
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
                    className="sticky-filter-bar" # Fixed to top on scroll
                ),

                # Row 3: KPI Cards
                dbc.Row(
                    [   # Column 1: Total Sales
                        dbc.Col(
                            html.Div(
                                [
                                    html.H6("TOTAL SALES", className="text-muted fw-bold mb-0 small"),
                                    html.H3(id="kpi-sales-value", className="text-dark fw-bold mb-0")
                                ],
                                className="kpi-card kpi-sales p-2"
                            ),
                            width=3
                        ),
                        # Column 2: Total Orders
                        dbc.Col(
                            html.Div(
                                [
                                    html.H6("TOTAL ORDERS", className="text-muted fw-bold mb-0 small"),
                                    html.H3(id="kpi-orders-value", className="text-dark fw-bold mb-0")
                                ],
                                className="kpi-card kpi-orders p-2"
                            ),
                            width=3
                        ),
                        # Column 3: Total Quantity
                        dbc.Col(
                            html.Div(
                                [
                                    html.H6("TOTAL QUANTITY", className="text-muted fw-bold mb-0 small"),
                                    html.H3(id="kpi-quantity-value", className="text-dark fw-bold mb-0")
                                ],
                                className="kpi-card kpi-quantity p-2"
                            ),
                            width=3
                        ),
                        # Column 4: Total Customers
                        dbc.Col(
                            html.Div(
                                [
                                    html.H6("TOTAL CUSTOMERS", className="text-muted fw-bold mb-0 small"),
                                    html.H3(id="kpi-customers-value", className="text-dark fw-bold mb-0")
                                ],
                                className="kpi-card kpi-customers p-2"
                            ),
                            width=3
                        )
                    ],
                    className="g-2 mb-3"
                ),

                # Row 4: Interactive Charts Section
                dbc.Row(
                    [
                        # Chart 1: Revenue Trend Over Time (7-Column Width)
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Sales Revenue Performance", className="card-title fw-bold text-dark mb-1"),
                                        dcc.Graph(
                                            id="sales-trend-graph",
                                            config={"displayModeBar": False}
                                        )
                                    ],
                                    className="p-2"
                                ),
                                className="shadow-sm border-0 mb-3"
                            ),
                            width=12, lg=7
                        ),

                        # Chart 2: Product Category Distribution (5-Column Width)
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Revenue by Category", className="card-title fw-bold text-dark mb-1"),
                                        dcc.Graph(
                                            id="category-pie-graph",
                                            config={"displayModeBar": False}
                                        )
                                    ],
                                    className="p-2"
                                ),
                                className="shadow-sm border-0 mb-3"
                            ),
                            width=12, lg=5
                        )
                    ],
                    className="mt-1"
                ),

                # Row 5: Top Products & Regional Performance Breakdown
                dbc.Row(
                    [

                        # Chart 3: Top 10 Products by Revenue (6 Columns)
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Top 10 Products by Revenue", className="card-title fw-bold text-dark mb-3"),
                                        dcc.Graph(
                                            id="top-products-graph",
                                            config={"displayModeBar": False}
                                        )
                                    ]
                                ),
                                className="shadow-sm border-0 mb-4 h-100"
                            ),
                            width=12, lg=6
                        ),

                        # Chart 4: Revenue by Region / Country (6 Columns)
                        dbc.Col(
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.H5("Regional Revenue Breakdown", className="card-title fw-bold text-dark mb-3"),
                                        dcc.Graph(
                                            id="regional-sales-graph",
                                            config={"displayModeBar": False}
                                        )
                                    ]
                                ),
                                className="shadow-sm border-0 mb-4 h-100"
                            ),
                            width=12, lg=6
                        )
                    ], 
                    className="mt-2")

            ],
            fluid=False
        ),

        # Modal
        dbc.Modal(
            [
                dbc.ModalHeader(
                    dbc.ModalTitle(id="modal-product-title", className="fw-bold")
                ),
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


@app.callback(
    [
        Output("kpi-sales-value", "children"),
        Output("kpi-orders-value", "children"),
        Output("kpi-quantity-value", "children"),
        Output("kpi-customers-value", "children"),
    ],
    [
        Input("date-picker-range", "start_date"),
        Input("date-picker-range", "end_date"),
        Input("category-dropdown", "value"),
        Input("country-dropdown", "value")
    ],
)
def update_all_kpis(start_date, end_date, selected_category, selected_country):
    if not start_date or not end_date:
        return "$0", "0", "0", "0"

    mask = (df_merged["order_date"] >= pd.to_datetime(start_date)) & (
        df_merged["order_date"] <= pd.to_datetime(end_date)
    )

    if selected_category and selected_category != "ALL":
        mask = mask & (df_merged["category"] == selected_category)

    if selected_country and selected_country != "ALL":
        mask = mask & (df_merged["country"] == selected_country)

    filtered_df = df_merged.loc[mask]

    total_sales = filtered_df["gross_sales_amount"].sum()
    total_orders = filtered_df["order_number"].nunique()
    total_quantity = filtered_df["quantity"].sum()
    total_customers = filtered_df["customer_key"].nunique()

    return (
        f"${total_sales:,.0f}",
        f"{total_orders:,}",
        f"{total_quantity:,}",
        f"{total_customers:,}",
    )


# --- CHART 1 CALLBACK: Sales Revenue Trend ---
@app.callback(
    Output("sales-trend-graph", "figure"),
    [
        Input("date-picker-range", "start_date"),
        Input("date-picker-range", "end_date"),
        Input("category-dropdown", "value"),
        Input("country-dropdown", "value")
    ],
)
def update_sales_trend(start_date, end_date, selected_category, selected_country):
    if not start_date or not end_date:
        return px.line()

    mask = (df_merged["order_date"] >= pd.to_datetime(start_date)) & (
        df_merged["order_date"] <= pd.to_datetime(end_date)
    )

    if selected_category and selected_category != "ALL":
        mask = mask & (df_merged["category"] == selected_category)

    if selected_country and selected_country != "ALL":
        mask = mask & (df_merged["country"] == selected_country)

    filtered_df = df_merged.loc[mask]

    # Aggregate sales by month for a smooth line chart
    trend_df = (
        filtered_df.set_index("order_date")
        .resample("ME")["gross_sales_amount"]
        .sum()
        .reset_index()
    )

    # Plotly Area/Line Chart matching the Sales KPI green color (#2ecc71)
    fig = px.area(
        trend_df,
        x="order_date",
        y="gross_sales_amount",
        labels={"order_date": "", "gross_sales_amount": "Revenue ($)"},
    )

    fig.update_traces(
        line_color="#2ecc71",
        fillcolor="rgba(46, 204, 113, 0.15)",
        hovertemplate="<b>Date:</b> %{x|%b %Y}<br><b>Revenue:</b> $%{y:,.0f}<extra></extra>"
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
@app.callback(
    Output("category-pie-graph", "figure"),
    [
        Input("date-picker-range", "start_date"),
        Input("date-picker-range", "end_date"),
        Input("category-dropdown", "value"),
        Input("country-dropdown", "value")
    ],
)
def update_category_pie(start_date, end_date, selected_category, selected_country):
    if not start_date or not end_date:
        return px.pie()

    # 1. Base filter for Date Range
    mask = (df_merged["order_date"] >= pd.to_datetime(start_date)) & (
        df_merged["order_date"] <= pd.to_datetime(end_date)
    )

    # 2. Category filter
    if selected_category and selected_category != "ALL":
        mask = mask & (df_merged["category"] == selected_category)

    # 3. Country filter
    if selected_country and selected_country != "ALL":
        mask = mask & (df_merged["country"] == selected_country)

    filtered_df = df_merged.loc[mask]

    # Aggregate total gross sales by category
    cat_df = (
        filtered_df.groupby("category")["gross_sales_amount"]
        .sum()
        .reset_index()
    )

    # Format category names cleanly (Capitalized)
    cat_df["category"] = cat_df["category"].astype(str).str.title()

    # Create Donut Chart
    fig = px.pie(
        cat_df,
        names="category",
        values="gross_sales_amount",
        hole=0.55, # Converts standard pie into an executive donut chart
        color_discrete_sequence=["#2ecc71", "#3498db", "#9b59b6", "#f39c12", "#e74c3c"] # Palette aligned with KPI cards
    )

    fig.update_traces(
        textinfo="percent+label",
        hovertemplate="<b>Category:</b> %{label}<br><b>Revenue:</b> $%{value:,.0f} (%{percent})<extra></extra>",
        marker=dict(line=dict(color="#ffffff", width=2)) # Clean white separation lines
    )

    fig.update_layout(
        showlegend=False, # Labels on slices keep it clutter-free
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=260
    )

    return fig

# --- CHART 3 CALLBACK: Top 10 Products by Revenue ---
@app.callback(
    Output("top-products-graph", "figure"),
    [
        Input("date-picker-range", "start_date"),
        Input("date-picker-range", "end_date"),
        Input("category-dropdown", "value"),
        Input("country-dropdown", "value"),
    ],
)
def update_top_products(
    start_date, end_date, selected_category, selected_country
):
    if not start_date or not end_date:
        return px.bar()

    mask = (df_merged["order_date"] >= pd.to_datetime(start_date)) & (
        df_merged["order_date"] <= pd.to_datetime(end_date)
    )

    if selected_category and selected_category != "ALL":
        mask = mask & (df_merged["category"] == selected_category)

    if selected_country and selected_country != "ALL":
        mask = mask & (df_merged["country"] == selected_country)

    filtered_df = df_merged.loc[mask]

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
        cliponaxis=False,  # Prevents labels from getting clipped by the axis boundary
    )

    # 1. Get max sales amount for padding calculation
    max_val = (
        top_products_df["gross_sales_amount"].max()
        if not top_products_df.empty
        else 0
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

    # 2. Extend x-axis max by 15% so outside text always fits safely inside the canvas
    fig.update_xaxes(range=[0, max_val * 1.15])

    return fig

# --- CHART 4 CALLBACK: Regional Revenue Breakdown ---
@app.callback(
    Output("regional-sales-graph", "figure"),
    [
        Input("date-picker-range", "start_date"),
        Input("date-picker-range", "end_date"),
        Input("category-dropdown", "value"),
        Input("country-dropdown", "value"),
    ],
)
def update_regional_sales(start_date, end_date, selected_category, selected_country):
    if not start_date or not end_date:
        return px.bar()

    mask = (df_merged["order_date"] >= pd.to_datetime(start_date)) & (
        df_merged["order_date"] <= pd.to_datetime(end_date)
    )

    if selected_category and selected_category != "ALL":
        mask = mask & (df_merged["category"] == selected_category)

    if selected_country and selected_country != "ALL":
        mask = mask & (df_merged["country"] == selected_country)

    filtered_df = df_merged.loc[mask]

    # Aggregate revenue by country
    region_df = (
        filtered_df.groupby("country")["gross_sales_amount"]
        .sum()
        .reset_index()
        .sort_values(by="gross_sales_amount", ascending=False)
    )

    # Capitalize country names cleanly
    region_df["country"] = region_df["country"].astype(str).str.title()

    fig = px.bar(
        region_df,
        x="country",
        y="gross_sales_amount",
        labels={"gross_sales_amount": "Revenue ($)", "country": ""},
        text_auto="$,.0f"
    )

    fig.update_traces(
        marker_color="#9b59b6", # Matching Purple accent color
        hovertemplate="<b>Country:</b> %{x}<br><b>Revenue:</b> $%{y:,.0f}<extra></extra>",
        textposition="outside",
        cliponaxis=False
    )

    # Calculate padding safely with float casting
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

# MODAL CALLBACK (UPDATED WITH GLOBAL FILTER STATES)
@app.callback(
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
        Input("date-picker-range", "start_date"),
        Input("date-picker-range", "end_date"),
        Input("category-dropdown", "value"),
        Input("country-dropdown", "value")
    ],
    prevent_initial_call=True
)
def toggle_product_modal(clickData, close_clicks, start_date, end_date, selected_category, selected_country):
    from dash import callback_context
    ctx = callback_context
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

    # Handle Modal Close Button Click
    if trigger_id == "close-modal-btn":
        return False, "", None, None

    # Handle Chart Click Trigger
    if trigger_id == "top-products-graph" and clickData:
        # Extract product name from Plotly payload
        product_name = clickData["points"][0]["y"]

        # 1. Apply active global filters
        mask = (df_merged["order_date"] >= pd.to_datetime(start_date)) & (
            df_merged["order_date"] <= pd.to_datetime(end_date)
        )

        if selected_category and selected_category != "ALL":
            mask = mask & (df_merged["category"] == selected_category)

        if selected_country and selected_country != "ALL":
            mask = mask & (df_merged["country"] == selected_country)

        # 2. Filter for specific product
        product_df = df_merged.loc[mask & (df_merged["product_name"] == product_name)].copy()

        # Build Mini Modal KPIs
        total_rev = product_df["gross_sales_amount"].sum()
        total_qty = product_df["quantity"].sum()
        total_orders = product_df["order_number"].nunique()

        kpi_summary = dbc.Row([
            dbc.Col(html.Div([html.Small("Revenue", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"${total_rev:,.0f}", className="fs-5")]), width=4),
            dbc.Col(html.Div([html.Small("Units Sold", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"{total_qty:,}", className="fs-5")]), width=4),
            dbc.Col(html.Div([html.Small("Total Orders", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"{total_orders:,}", className="fs-5")]), width=4),
        ], className="bg-light p-3 rounded mb-3 text-center border")

        # Format table dataset (top 50 recent orders)
        records_df = (
            product_df[["order_number", "order_date", "first_name", "last_name", "country", "quantity", "gross_sales_amount"]]
            .sort_values(by="order_date", ascending=False)
            .head(50)
        )
        records_df["customer_name"] = records_df["first_name"] + " " + records_df["last_name"]
        records_df["order_date"] = records_df["order_date"].dt.strftime("%Y-%m-%d")

        # Build Granular Data Table with Clean Alignment & Typography
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
            style_header={
                "backgroundColor": "#f8f9fa",
                "fontWeight": "bold",
                "color": "#2c3e50",
                "textAlign": "left" # Match cell text alignment
            },
            style_cell={
                "padding": "10px 14px",
                "fontSize": "0.85rem",
                "fontFamily": "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
                "textAlign": "left"
            },
            style_cell_conditional=[
                {"if": {"column_id": "quantity"}, "textAlign": "right"},
                {"if": {"column_id": "gross_sales_amount"}, "textAlign": "right"},
            ],
            style_header_conditional=[
                {"if": {"column_id": "quantity"}, "textAlign": "right"},
                {"if": {"column_id": "gross_sales_amount"}, "textAlign": "right"},
            ],
            style_data_conditional=[
                {"if": {"row_index": "odd"}, "backgroundColor": "#fcfcfc"}
            ]
        )

        return True, f"Product Details: {product_name}", kpi_summary, detail_table

    return False, "", None, None

if __name__ == "__main__":
    app.run(debug=True)
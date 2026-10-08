import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px

# pyrefly: ignore [missing-import]
from components.filter_bar import create_filter_bar

# pyrefly: ignore [missing-import]
from components.kpi_bar import create_kpi_bar

# pyrefly: ignore [missing-import]
from components.panels import chart_panel, create_grid, loading, panel

# pyrefly: ignore [missing-import]
from components.revenue_chart import map_figure, normalize_view, revenue_menu
from dash import (
    Input,
    Output,
    State,
    callback,
    callback_context,
    dcc,
    html,
    no_update,
)

# pyrefly: ignore [missing-import]
from data_loader import get_prepared_dataset

# pyrefly: ignore [missing-import]
from theme import COLORS, style_figure

# pyrefly: ignore [missing-import]
from utils.helpers import calculate_pop_badge, filter_dataframe, format_compact_number

# Register Page
dash.register_page(__name__, path="/dashboard", name="Product Overview")


def layout():
    return html.Div(
        [
            html.Div(id="overview-page-loaded", hidden=True),
            dcc.Store(id="overview-revenue-view", storage_type="session", data="donut"),
            html.Div(
                id="overview-filter-bar-container",
                children=create_filter_bar(
                    pd.DataFrame(),
                    date_picker_id="date-picker-range",
                    category_dropdown_id="category-dropdown",
                    country_dropdown_id="country-dropdown",
                ),
            ),
            loading(
                create_kpi_bar(
                    [
                        ("Total revenue", "kpi-sales"),
                        ("Orders", "kpi-orders"),
                        ("Units sold", "kpi-quantity"),
                        ("Customers", "kpi-customers"),
                    ]
                ),
                "kpi-loading",
            ),
            html.Div(
                [
                    chart_panel(
                        "Sales revenue",
                        "sales-trend-graph",
                        "sales-trend-loading",
                        "span-8",
                    ),
                    chart_panel(
                        "Revenue by category",
                        "category-pie-graph",
                        "category-pie-loading",
                        "span-4",
                        actions=revenue_menu(),
                        title_id="overview-revenue-title",
                        footer=html.Div(id="overview-revenue-details"),
                    ),
                    panel(
                        "Top-performing products",
                        [
                            loading(
                                create_grid(
                                    [
                                        {
                                            "field": "product_name",
                                            "headerName": "Product",
                                            "flex": 2,
                                        },
                                        {
                                            "field": "units",
                                            "headerName": "Units",
                                            "type": "numericColumn",
                                        },
                                        {
                                            "field": "revenue",
                                            "headerName": "Revenue",
                                            "type": "numericColumn",
                                            "valueFormatter": {
                                                "function": "d3.format('$,.0f')(params.value)"
                                            },
                                        },
                                    ],
                                    grid_id="top-products-grid",
                                    options={
                                        "rowSelection": {
                                            "mode": "singleRow",
                                            "enableClickSelection": True,
                                        }
                                    },
                                    row_id="params.data.product_name",
                                ),
                                "top-products-loading",
                            ),
                            html.Button(
                                "View selected product",
                                id="view-product-btn",
                                className="table-detail-btn",
                            ),
                        ],
                        "span-8",
                        "Select a product to explore its recent transactions.",
                    ),
                    chart_panel(
                        "Revenue by country",
                        "regional-sales-graph",
                        "regional-sales-loading",
                        "span-4",
                    ),
                ],
                className="dashboard-grid",
            ),
            dbc.Modal(
                [
                    dbc.ModalHeader(
                        dbc.ModalTitle(id="modal-product-title", className="fw-bold")
                    ),
                    dbc.ModalBody(
                        [
                            html.Div(id="modal-product-kpis", className="mb-3"),
                            html.H6(
                                "Recent Transactions",
                                className="fw-bold text-muted mb-2",
                            ),
                            dcc.Loading(
                                id="modal-table-loading",
                                type="circle",
                                color=COLORS["spinner"],
                                children=html.Div(id="modal-product-table-container"),
                                fullscreen=False,
                            ),
                        ]
                    ),
                    dbc.ModalFooter(
                        [
                            dbc.Button(
                                [
                                    html.I(className="bi bi-download me-2"),
                                    html.Span("Export Product Data"),
                                ],
                                id="export-product-detail-btn",
                                color="success",
                                className="fw-semibold me-auto",
                            ),
                            dcc.Download(id="product-detail-download-file"),
                            dbc.Button(
                                "Close",
                                id="close-modal-btn",
                                className="ms-auto",
                                color="secondary",
                            ),
                        ]
                    ),
                ],
                id="product-detail-modal",
                size="xl",
                is_open=False,
                centered=True,
            ),
        ],
        className="dashboard-container",
    )


# --- ASYNC FILTER BAR POPULATION ON LOAD ---
@callback(
    Output("overview-filter-bar-container", "children"),
    Input("overview-page-loaded", "id"),
)
def populate_overview_filter_bar(_):
    df_merged = get_prepared_dataset()
    return create_filter_bar(
        df_merged,
        date_picker_id="date-picker-range",
        category_dropdown_id="category-dropdown",
        country_dropdown_id="country-dropdown",
    )


# --- FILTER STORE SYNC CALLBACK ---
@callback(
    Output("global-filter-store", "data", allow_duplicate=True),
    [
        Input("date-picker-range", "start_date"),
        Input("date-picker-range", "end_date"),
        Input("category-dropdown", "value"),
        Input("country-dropdown", "value"),
    ],
    prevent_initial_call=True,
)
def update_filter_store(start_date, end_date, category, country):
    return {
        "start_date": start_date,
        "end_date": end_date,
        "category": category,
        "country": country,
    }


# --- KPI CALLBACK ---
@callback(
    Output("kpi-sales-value", "children"),
    Output("kpi-orders-value", "children"),
    Output("kpi-quantity-value", "children"),
    Output("kpi-customers-value", "children"),
    Output("kpi-sales-tooltip", "children"),
    Output("kpi-orders-tooltip", "children"),
    Output("kpi-quantity-tooltip", "children"),
    Output("kpi-customers-tooltip", "children"),
    Output("kpi-sales-badge", "children"),
    Output("kpi-orders-badge", "children"),
    Output("kpi-quantity-badge", "children"),
    Output("kpi-customers-badge", "children"),
    Input("global-filter-store", "data"),
)
def update_all_kpis(filter_data):
    if not filter_data:
        return (no_update,) * 12

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    if not start_date or not end_date:
        return (no_update,) * 12

    df_merged = get_prepared_dataset()
    filtered_df = filter_dataframe(
        df_merged, start_date, end_date, selected_category, selected_country
    )

    # 1. Handle Empty DataFrame Case
    if filtered_df.empty:
        empty_tooltip = [html.Div("No data available", className="text-start")]
        empty_badge = html.Span("N/A", className="badge-soft-secondary")
        return (
            "$0",
            "0",
            "0",
            "0",
            empty_tooltip,
            empty_tooltip,
            empty_tooltip,
            empty_tooltip,
            empty_badge,
            empty_badge,
            empty_badge,
            empty_badge,
        )

    # 2. Main KPI Aggregations
    total_sales = filtered_df["gross_sales_amount"].sum()
    total_orders = filtered_df["order_number"].nunique()
    total_quantity = filtered_df["quantity"].sum()
    total_customers = filtered_df["customer_key"].nunique()

    # Format values with compact abbreviations
    sales_display = format_compact_number(total_sales, is_currency=True)
    orders_display = format_compact_number(total_orders, is_currency=False)
    quantity_display = format_compact_number(total_quantity, is_currency=False)
    customers_display = format_compact_number(total_customers, is_currency=False)

    # 3. Compute Dynamic Period-over-Period Badges
    sales_badge = calculate_pop_badge(
        df_merged,
        "order_date",
        "gross_sales_amount",
        start_date,
        end_date,
        "sum",
        selected_category,
        selected_country,
    )

    orders_badge = calculate_pop_badge(
        df_merged,
        "order_date",
        "order_number",
        start_date,
        end_date,
        "nunique",
        selected_category,
        selected_country,
    )

    quantity_badge = calculate_pop_badge(
        df_merged,
        "order_date",
        "quantity",
        start_date,
        end_date,
        "sum",
        selected_category,
        selected_country,
    )

    customers_badge = calculate_pop_badge(
        df_merged,
        "order_date",
        "customer_key",
        start_date,
        end_date,
        "nunique",
        selected_category,
        selected_country,
    )

    # 4. Tooltip Metrics
    active_days = filtered_df["order_date"].dt.date.nunique()

    aov = total_sales / total_orders if total_orders > 0 else 0
    daily_avg_sales = total_sales / active_days if active_days > 0 else 0
    sales_tooltip_content = [
        html.Div(f"• Avg Order Value (AOV): ${aov:,.2f}", className="text-start"),
        html.Div(
            f"• Daily Avg Revenue: ${daily_avg_sales:,.0f}", className="text-start"
        ),
    ]

    daily_avg_orders = total_orders / active_days if active_days > 0 else 0
    items_per_order = total_quantity / total_orders if total_orders > 0 else 0
    orders_tooltip_content = [
        html.Div(
            f"• Daily Avg Orders: {daily_avg_orders:,.1f}", className="text-start"
        ),
        html.Div(f"• Units Per Order: {items_per_order:,.1f}", className="text-start"),
    ]

    daily_avg_qty = total_quantity / active_days if active_days > 0 else 0
    avg_unit_price = total_sales / total_quantity if total_quantity > 0 else 0
    quantity_tooltip_content = [
        html.Div(f"• Daily Avg Units: {daily_avg_qty:,.1f}", className="text-start"),
        html.Div(
            f"• Effective Unit Price: ${avg_unit_price:,.2f}", className="text-start"
        ),
    ]

    rev_per_customer = total_sales / total_customers if total_customers > 0 else 0
    orders_per_customer = total_orders / total_customers if total_customers > 0 else 0
    customers_tooltip_content = [
        html.Div(
            f"• Revenue / Customer: ${rev_per_customer:,.2f}", className="text-start"
        ),
        html.Div(
            f"• Orders / Customer: {orders_per_customer:,.2f}", className="text-start"
        ),
    ]

    return (
        sales_display,
        orders_display,
        quantity_display,
        customers_display,
        sales_tooltip_content,
        orders_tooltip_content,
        quantity_tooltip_content,
        customers_tooltip_content,
        sales_badge,
        orders_badge,
        quantity_badge,
        customers_badge,
    )


# --- CHART 1 CALLBACK: Sales Revenue Trend ---
@callback(Output("sales-trend-graph", "figure"), Input("global-filter-store", "data"))
def update_sales_trend(filter_data):
    if not filter_data:
        return no_update

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    if not start_date or not end_date:
        return no_update

    df_merged = get_prepared_dataset()
    filtered_df = filter_dataframe(
        df_merged, start_date, end_date, selected_category, selected_country
    )

    if filtered_df.empty:
        return style_figure(px.area(title="No data for selected period"))

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
        line_color=COLORS["spinner"],
        fillcolor="rgba(46, 204, 113, 0.15)",
        hovertemplate="<b>Date:</b> %{x|%b %d, %Y}<br><b>Revenue:</b> $%{y:,.0f}<extra></extra>",
        line=dict(shape="linear", color=COLORS["spinner"], width=3),
    )

    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLORS["muted"]),
        xaxis=dict(showgrid=False, zeroline=False, color=COLORS["muted"]),
        yaxis=dict(
            showgrid=True,
            gridcolor=COLORS["border"],
            zeroline=False,
            color=COLORS["muted"],
        ),
        height=260,
    )

    return style_figure(fig)


# --- CHART 2 CALLBACK: Revenue by Product Category ---
@callback(
    Output("overview-revenue-view", "data"),
    Input("overview-revenue-donut", "n_clicks"),
    Input("overview-revenue-map", "n_clicks"),
    prevent_initial_call=True,
)
def select_revenue_view(donut_clicks, map_clicks):
    return "map" if callback_context.triggered_id == "overview-revenue-map" else "donut"


@callback(
    Output("category-pie-graph", "figure"),
    Output("overview-revenue-title", "children"),
    Output("overview-revenue-details", "children"),
    Output("overview-revenue-donut", "active"),
    Output("overview-revenue-map", "active"),
    Input("global-filter-store", "data"),
    Input("overview-revenue-view", "data"),
)
def update_category_pie(filter_data, view="donut"):
    view = normalize_view(view)
    title = "Revenue by country" if view == "map" else "Revenue by category"

    def result(figure, details=None):
        return figure, title, details, view == "donut", view == "map"

    if not filter_data:
        return result(style_figure(px.scatter(title="Select a date range")))

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    if not start_date or not end_date:
        return result(style_figure(px.scatter(title="Select a date range")))

    df_merged = get_prepared_dataset()
    filtered_df = filter_dataframe(
        df_merged, start_date, end_date, selected_category, selected_country
    )

    if filtered_df.empty:
        return result(style_figure(px.scatter(title="No data for selected period")))

    if view == "map":
        figure, details = map_figure(filtered_df)
        return result(figure, details)

    cat_df = filtered_df.groupby("category")["gross_sales_amount"].sum().reset_index()

    cat_df["category"] = cat_df["category"].astype(str).str.title()

    fig = px.pie(
        cat_df,
        names="category",
        values="gross_sales_amount",
        hole=0.55,
        color_discrete_sequence=[
            COLORS["success"],
            COLORS["accent"],
            COLORS["purple"],
            COLORS["warning"],
            COLORS["danger"],
        ],
    )

    fig.update_traces(
        textinfo="percent+label",
        hovertemplate="<b>Category:</b> %{label}<br><b>Revenue:</b> $%{value:,.0f} (%{percent})<extra></extra>",
        marker=dict(line=dict(color=COLORS["text"], width=2)),
    )

    fig.update_layout(
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLORS["muted"]),
        xaxis=dict(showgrid=False, zeroline=False, color=COLORS["muted"]),
        yaxis=dict(
            showgrid=True,
            gridcolor=COLORS["border"],
            zeroline=False,
            color=COLORS["muted"],
        ),
        height=260,
    )

    return result(style_figure(fig))


# --- CHART 3 CALLBACK: Top 10 Products by Revenue ---
@callback(Output("top-products-grid", "rowData"), Input("global-filter-store", "data"))
def update_top_products(filter_data):
    if not filter_data:
        return []
    df_merged = get_prepared_dataset()
    filtered = filter_dataframe(
        df_merged,
        filter_data.get("start_date"),
        filter_data.get("end_date"),
        filter_data.get("category"),
        filter_data.get("country"),
    )
    if filtered.empty:
        return []
    return (
        filtered.groupby("product_name")
        .agg(revenue=("gross_sales_amount", "sum"), units=("quantity", "sum"))
        .reset_index()
        .sort_values("revenue", ascending=False)
        .head(10)
        .to_dict("records")
    )


# --- CHART 4 CALLBACK: Regional Revenue Breakdown ---
@callback(
    Output("regional-sales-graph", "figure"), Input("global-filter-store", "data")
)
def update_regional_sales(filter_data):
    if not filter_data:
        return no_update

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category")
    selected_country = filter_data.get("country")

    if not start_date or not end_date:
        return no_update

    df_merged = get_prepared_dataset()
    filtered_df = filter_dataframe(
        df_merged, start_date, end_date, selected_category, selected_country
    )

    if filtered_df.empty:
        return style_figure(px.bar(title="No data for selected period"))

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
        text_auto="$,.0f",
    )

    fig.update_traces(
        marker_color=COLORS["purple"],
        hovertemplate="<b>Country:</b> %{x}<br><b>Revenue:</b> $%{y:,.0f}<extra></extra>",
        textposition="outside",
        cliponaxis=False,
    )

    raw_max = region_df["gross_sales_amount"].max() if not region_df.empty else 0
    max_val = float(raw_max) if raw_max is not None else 0.0

    fig.update_layout(
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLORS["muted"]),
        xaxis=dict(showgrid=False, zeroline=False, color=COLORS["muted"]),
        yaxis=dict(
            showgrid=True,
            gridcolor=COLORS["border"],
            zeroline=False,
            color=COLORS["muted"],
        ),
        height=350,
    )

    fig.update_yaxes(range=[0, max_val * 1.15])

    return style_figure(fig)


# --- MODAL CALLBACK ---
@callback(
    [
        Output("product-detail-modal", "is_open"),
        Output("modal-product-title", "children"),
        Output("modal-product-kpis", "children"),
        Output("modal-product-table-container", "children"),
    ],
    [
        Input("top-products-grid", "cellClicked"),
        Input("view-product-btn", "n_clicks"),
        Input("close-modal-btn", "n_clicks"),
    ],
    [State("global-filter-store", "data"), State("top-products-grid", "selectedRows")],
    prevent_initial_call=True,
)
def toggle_product_modal(
    clickData, view_clicks, close_clicks, filter_data, selected_rows
):
    ctx = callback_context
    if not ctx.triggered:
        return False, "", None, None

    # pyrefly: ignore [unsupported-operation]
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if trigger_id == "close-modal-btn":
        return False, "", None, None

    if trigger_id in ("top-products-grid", "view-product-btn"):
        product_name = (
            (selected_rows or [{}])[0].get("product_name")
            if trigger_id == "view-product-btn"
            else (clickData or {}).get("rowId")
        )
        if not product_name:
            return no_update, no_update, no_update, no_update

        filter_data = filter_data or {}
        start_date = filter_data.get("start_date")
        end_date = filter_data.get("end_date")
        selected_category = filter_data.get("category")
        selected_country = filter_data.get("country")

        df_merged = get_prepared_dataset()
        filtered_df = filter_dataframe(
            df_merged, start_date, end_date, selected_category, selected_country
        )
        product_df = filtered_df.loc[filtered_df["product_name"] == product_name].copy()

        if product_df.empty:
            return (
                True,
                f"Product Details: {product_name}",
                None,
                html.Div(
                    "No transactions found within the selected date range.",
                    className="p-3 text-muted text-center fw-bold",
                ),
            )

        total_rev = product_df["gross_sales_amount"].sum()
        total_qty = product_df["quantity"].sum()
        total_orders = product_df["order_number"].nunique()

        kpi_summary = dbc.Row(
            [
                dbc.Col(
                    html.Div(
                        [
                            html.Small(
                                "Revenue",
                                className="text-muted d-block text-uppercase fw-semibold",
                            ),
                            html.Strong(
                                f"${total_rev:,.0f}", className="fs-5 text-white"
                            ),
                        ]
                    ),
                    width=4,
                ),
                dbc.Col(
                    html.Div(
                        [
                            html.Small(
                                "Units Sold",
                                className="text-muted d-block text-uppercase fw-semibold",
                            ),
                            html.Strong(f"{total_qty:,}", className="fs-5 text-white"),
                        ]
                    ),
                    width=4,
                ),
                dbc.Col(
                    html.Div(
                        [
                            html.Small(
                                "Total Orders",
                                className="text-muted d-block text-uppercase fw-semibold",
                            ),
                            html.Strong(
                                f"{total_orders:,}", className="fs-5 text-white"
                            ),
                        ]
                    ),
                    width=4,
                ),
            ],
            className="dark-card p-3 rounded mb-3 text-center border",
        )

        records_df = (
            product_df[
                [
                    "order_number",
                    "order_date",
                    "first_name",
                    "last_name",
                    "country",
                    "quantity",
                    "gross_sales_amount",
                ]
            ]
            .sort_values(by="order_date", ascending=False)
            .head(50)
        )
        records_df["customer_name"] = (
            records_df["first_name"].fillna("")
            + " "
            + records_df["last_name"].fillna("")
        )
        records_df["order_date"] = records_df["order_date"].dt.strftime("%Y-%m-%d")

        column_defs = [
            {"field": "order_number", "headerName": "Order #"},
            {"field": "order_date", "headerName": "Date"},
            {"field": "customer_name", "headerName": "Customer"},
            {"field": "country", "headerName": "Country"},
            {"field": "quantity", "headerName": "Qty", "type": "rightAligned"},
            {
                "field": "gross_sales_amount",
                "headerName": "Revenue ($)",
                "type": "rightAligned",
                "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"},
            },
        ]

        detail_table = create_grid(
            column_defs, records_df.to_dict("records"), class_name="detail-grid"
        )

        return True, f"Product Details: {product_name}", kpi_summary, detail_table

    return False, "", None, None


# --- CALLBACK: Export Button ---
@callback(
    Output("product-detail-download-file", "data"),
    Input("export-product-detail-btn", "n_clicks"),
    [State("modal-product-title", "children"), State("global-filter-store", "data")],
    prevent_initial_call=True,
)
def export_selected_product_details(n_clicks, product_title, filter_data):
    if not n_clicks or not product_title or not filter_data:
        return no_update

    product_name = product_title.removeprefix("Product Details: ")

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category", "ALL")
    selected_country = filter_data.get("country", "ALL")

    df_merged = get_prepared_dataset()
    filtered_df = filter_dataframe(
        df_merged, start_date, end_date, selected_category, selected_country
    )
    product_df = filtered_df[filtered_df["product_name"] == product_name].copy()

    if product_df.empty:
        return no_update

    product_df["customer_name"] = (
        product_df["first_name"].fillna("") + " " + product_df["last_name"].fillna("")
    )

    export_df = product_df[
        [
            "order_number",
            "order_date",
            "customer_name",
            "country",
            "category",
            "quantity",
            "gross_sales_amount",
        ]
    ].rename(
        columns={
            "order_number": "Order Number",
            "order_date": "Order Date",
            "customer_name": "Customer",
            "country": "Country",
            "category": "Category",
            "quantity": "Quantity",
            "gross_sales_amount": "Revenue ($)",
        }
    )

    safe_product_name = "".join([c if c.isalnum() else "_" for c in product_name])
    filename = f"{safe_product_name}_transactions_{start_date}_to_{end_date}.csv"

    return dcc.send_data_frame(export_df.to_csv, filename=filename, index=False)

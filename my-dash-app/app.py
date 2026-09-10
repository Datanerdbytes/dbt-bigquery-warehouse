import dash
from dash import Dash, html, dcc, callback, Input, Output, State, callback_context, no_update
import dash_bootstrap_components as dbc
import dash_ag_grid as dag
import pandas as pd
from flask_caching import Cache
from utils.cache import cache
from components.sidebar import create_sidebar
from components.header import create_header  
from utils.helpers import filter_dataframe
from data_loader import load_and_prep_data

# Initialize App
app = Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[
        dbc.themes.DARKLY,
        dbc.icons.BOOTSTRAP 
    ],
    suppress_callback_exceptions=True
)

cache.init_app(app.server)
server = app.server

app.layout = html.Div(
    [   
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="global-filter-store", storage_type="session"),
        create_sidebar(),
        html.Div(
            [
                create_header(),  
                dash.page_container
            ],
            className="main-content-wrapper p-4"
        )
    ],
    className="d-flex app-wrapper"
)

# Helper function to create standard preview grids
def create_preview_grid(df, column_defs, height="200px"):
    return dag.AgGrid(
        rowData=df.to_dict("records"),
        columnDefs=column_defs,
        dashGridOptions={"theme": "themeBalham", "animateRows": True, "pagination": False},
        columnSize="responsiveSizeToFit",
        defaultColDef={"filter": False, "sortable": True},
        style={"height": height, "width": "100%"}
    )

# --- CALLBACK 1: TOGGLE & RENDER EXPORT PREVIEW MODAL ---
@callback(
    [
        Output("export-preview-modal", "is_open"),
        Output("export-modal-body-content", "children")
    ],
    [
        Input("global-export-btn", "n_clicks"),
        Input("close-export-modal-btn", "n_clicks")
    ],
    [
        State("global-filter-store", "data"),
        State("url", "pathname"),
        State("export-preview-modal", "is_open")
    ],
    prevent_initial_call=True
)
def toggle_and_render_export_modal(open_clicks, close_clicks, filter_data, pathname, is_open):
    ctx = callback_context
    if not ctx.triggered:
        return False, no_update

    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if trigger_id == "close-export-modal-btn":
        return False, no_update

    if trigger_id == "global-export-btn":
        if not filter_data:
            return True, html.Div("No filter parameters selected.", className="text-muted p-3 text-center")

        start_date = filter_data.get("start_date")
        end_date = filter_data.get("end_date")
        selected_category = filter_data.get("category", "ALL")
        selected_country = filter_data.get("country", "ALL")

        df_merged, _, _, _, _ = load_and_prep_data()
        filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

        if filtered_df.empty:
            return True, html.Div("No transaction data available for the active selections.", className="text-muted p-3 text-center")

        # --- ROUTE: CUSTOMER 360 SUMMARY ---
        if pathname == "/customers":
            curr_summary = filtered_df.groupby("customer_key").agg(
                total_spend=("gross_sales_amount", "sum"),
                total_orders=("order_number", "nunique"),
                total_units=("quantity", "sum")
            ).reset_index()

            curr_cust = len(curr_summary)
            curr_spend = curr_summary["total_spend"].sum() / curr_cust if curr_cust > 0 else 0
            curr_freq = curr_summary["total_orders"].sum() / curr_cust if curr_cust > 0 else 0
            curr_repeat_cnt = (curr_summary["total_orders"] > 1).sum()
            curr_repeat_rate = (curr_repeat_cnt / curr_cust * 100) if curr_cust > 0 else 0

            kpi_summary_cards = dbc.Row([
                dbc.Col(html.Div([html.Small("Active Customers", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"{curr_cust:,}", className="fs-5 text-white")]), width=3),
                dbc.Col(html.Div([html.Small("Avg Spend / Cust", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"${curr_spend:,.0f}", className="fs-5 text-white")]), width=3),
                dbc.Col(html.Div([html.Small("Avg Order Freq", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"{curr_freq:,.2f}", className="fs-5 text-white")]), width=3),
                dbc.Col(html.Div([html.Small("Repeat Rate", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"{curr_repeat_rate:.1f}%", className="fs-5 text-white")]), width=3),
            ], className="dark-card p-3 rounded mb-4 text-center border")

            # Top High-Value Champions
            top_cust = (
                filtered_df.groupby(["first_name", "last_name", "country"])
                .agg(total_spend=("gross_sales_amount", "sum"), total_orders=("order_number", "nunique"))
                .reset_index().sort_values(by="total_spend", ascending=False).head(10)
            )
            top_cust["customer_name"] = top_cust["first_name"].fillna("") + " " + top_cust["last_name"].fillna("")

            champ_cols = [
                {"field": "customer_name", "headerName": "Customer"},
                {"field": "country", "headerName": "Country"},
                {"field": "total_orders", "headerName": "Orders", "type": "rightAligned"},
                {"field": "total_spend", "headerName": "Total Spend", "type": "rightAligned", "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"}},
            ]
            champ_grid = create_preview_grid(top_cust, champ_cols, height="220px")

            # RFM Segment Breakdown
            max_ref_date = pd.to_datetime(end_date)
            temp_df = filtered_df.copy()
            temp_df["order_date"] = pd.to_datetime(temp_df["order_date"])

            rfm = (
                temp_df.groupby("customer_key")
                .agg(recency=("order_date", lambda x: (max_ref_date - x.max()).days), frequency=("order_number", "nunique"), monetary=("gross_sales_amount", "sum"))
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
            rfm_summary = (
                rfm.groupby("Segment")
                .agg(Customer_Count=("customer_key", "count"), Total_Segment_Spend=("monetary", "sum"), Avg_Spend_Per_Customer=("monetary", "mean"))
                .reset_index().sort_values(by="Customer_Count", ascending=False)
            )

            rfm_cols = [
                {"field": "Segment", "headerName": "RFM Segment"},
                {"field": "Customer_Count", "headerName": "Customers", "type": "rightAligned"},
                {"field": "Total_Segment_Spend", "headerName": "Total Spend", "type": "rightAligned", "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"}},
                {"field": "Avg_Spend_Per_Customer", "headerName": "Avg Spend / Cust", "type": "rightAligned", "valueFormatter": {"function": "d3.format('$,.2f')(params.value)"}},
            ]
            rfm_grid = create_preview_grid(rfm_summary, rfm_cols, height="180px")

            modal_body = html.Div([
                html.Div(f"Customer 360 Analysis | Date Range: {start_date} to {end_date} | Category: {selected_category} | Region: {selected_country}", className="text-muted small mb-3"),
                kpi_summary_cards,
                html.H6("Top High-Value Champions", className="fw-bold text-white mb-2"),
                html.Div(champ_grid, className="mb-4"),
                html.H6("Customer RFM Segmentation", className="fw-bold text-white mb-2"),
                html.Div(rfm_grid, className="mb-2")
            ])

            return True, modal_body

        # --- DEFAULT ROUTE: PRODUCT OVERVIEW SUMMARY ---
        else:
            total_sales = filtered_df["gross_sales_amount"].sum()
            total_orders = filtered_df["order_number"].nunique()
            total_units = filtered_df["quantity"].sum()
            aov = total_sales / total_orders if total_orders > 0 else 0

            kpi_summary_cards = dbc.Row([
                dbc.Col(html.Div([html.Small("Revenue", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"${total_sales:,.0f}", className="fs-5 text-white")]), width=3),
                dbc.Col(html.Div([html.Small("Total Orders", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"{total_orders:,}", className="fs-5 text-white")]), width=3),
                dbc.Col(html.Div([html.Small("Units Sold", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"{total_units:,}", className="fs-5 text-white")]), width=3),
                dbc.Col(html.Div([html.Small("Avg Order Value", className="text-muted d-block text-uppercase fw-semibold"), html.Strong(f"${aov:,.2f}", className="fs-5 text-white")]), width=3),
            ], className="dark-card p-3 rounded mb-4 text-center border")

            top_products_df = (
                filtered_df.groupby("product_name")
                .agg(Revenue=("gross_sales_amount", "sum"), Units_Sold=("quantity", "sum"), Orders=("order_number", "nunique"))
                .reset_index().sort_values(by="Revenue", ascending=False).head(10)
            )
            products_cols = [
                {"field": "product_name", "headerName": "Product Name"},
                {"field": "Revenue", "headerName": "Revenue", "type": "rightAligned", "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"}},
                {"field": "Units_Sold", "headerName": "Units Sold", "type": "rightAligned"},
                {"field": "Orders", "headerName": "Orders", "type": "rightAligned"},
            ]
            products_grid = create_preview_grid(top_products_df, products_cols, height="220px")

            modal_body = html.Div([
                html.Div(f"Product Overview | Date Range: {start_date} to {end_date} | Category: {selected_category} | Region: {selected_country}", className="text-muted small mb-3"),
                kpi_summary_cards,
                html.H6("Top 10 Performing Products", className="fw-bold text-white mb-2"),
                html.Div(products_grid, className="mb-2")
            ])

            return True, modal_body

    return False, no_update


# --- CALLBACK 2: EXECUTE CSV DOWNLOAD FROM MODAL ---
@callback(
    Output("global-download-file", "data"),
    Input("confirm-download-btn", "n_clicks"),
    [
        State("global-filter-store", "data"),
        State("url", "pathname")
    ],
    prevent_initial_call=True
)
def execute_csv_download(n_clicks, filter_data, pathname):
    if not n_clicks or not filter_data:
        return no_update

    start_date = filter_data.get("start_date")
    end_date = filter_data.get("end_date")
    selected_category = filter_data.get("category", "ALL")
    selected_country = filter_data.get("country", "ALL")

    df_merged, _, _, _, _ = load_and_prep_data()
    filtered_df = filter_dataframe(df_merged, start_date, end_date, selected_category, selected_country)

    if filtered_df.empty:
        return no_update

    if pathname == "/customers":
        curr_summary = filtered_df.groupby("customer_key").agg(
            total_spend=("gross_sales_amount", "sum"),
            total_orders=("order_number", "nunique")
        ).reset_index()

        curr_cust = len(curr_summary)
        curr_spend = curr_summary["total_spend"].sum() / curr_cust if curr_cust > 0 else 0
        curr_freq = curr_summary["total_orders"].sum() / curr_cust if curr_cust > 0 else 0
        curr_repeat_cnt = (curr_summary["total_orders"] > 1).sum()
        curr_repeat_rate = (curr_repeat_cnt / curr_cust * 100) if curr_cust > 0 else 0

        kpi_df = pd.DataFrame([
            {"Metric": "Date Range", "Value": f"{start_date} to {end_date}"},
            {"Metric": "Category Filter", "Value": selected_category},
            {"Metric": "Region Filter", "Value": selected_country},
            {"Metric": "Active Customers", "Value": curr_cust},
            {"Metric": "Avg Spend per Customer ($)", "Value": round(curr_spend, 2)},
            {"Metric": "Avg Order Frequency", "Value": round(curr_freq, 2)},
            {"Metric": "Repeat Rate (%)", "Value": f"{curr_repeat_rate:.1f}%"},
        ])

        top_cust = (
            filtered_df.groupby(["first_name", "last_name", "country"])
            .agg(Total_Spend=("gross_sales_amount", "sum"), Total_Orders=("order_number", "nunique"))
            .reset_index().sort_values(by="Total_Spend", ascending=False).head(10)
        )
        top_cust["Customer_Name"] = top_cust["first_name"].fillna("") + " " + top_cust["last_name"].fillna("")
        top_cust = top_cust[["Customer_Name", "country", "Total_Orders", "Total_Spend"]].rename(columns={"country": "Country"})

        csv_string = (
            "=== CUSTOMER 360 EXECUTIVE SUMMARY ===\n"
            + kpi_df.to_csv(index=False)
            + "\n=== TOP HIGH-VALUE CHAMPIONS ===\n"
            + top_cust.to_csv(index=False)
        )
        filename = f"customer_360_summary_{start_date}_to_{end_date}.csv"

    else:
        total_sales = filtered_df["gross_sales_amount"].sum()
        total_orders = filtered_df["order_number"].nunique()
        total_units = filtered_df["quantity"].sum()
        aov = total_sales / total_orders if total_orders > 0 else 0

        kpi_df = pd.DataFrame([
            {"Metric": "Date Range", "Value": f"{start_date} to {end_date}"},
            {"Metric": "Total Revenue ($)", "Value": round(total_sales, 2)},
            {"Metric": "Total Orders", "Value": total_orders},
            {"Metric": "Units Sold", "Value": total_units},
            {"Metric": "Average Order Value ($)", "Value": round(aov, 2)},
        ])

        top_products_df = (
            filtered_df.groupby("product_name")
            .agg(Revenue=("gross_sales_amount", "sum"), Units_Sold=("quantity", "sum"), Orders=("order_number", "nunique"))
            .reset_index().sort_values(by="Revenue", ascending=False).head(10)
        )

        csv_string = (
            "=== PRODUCT OVERVIEW EXECUTIVE SUMMARY ===\n"
            + kpi_df.to_csv(index=False)
            + "\n=== TOP 10 PRODUCTS BY REVENUE ===\n"
            + top_products_df.to_csv(index=False)
        )
        filename = f"product_overview_summary_{start_date}_to_{end_date}.csv"

    return dcc.send_string(csv_string, filename=filename)

if __name__ == "__main__":
    app.run(debug=True)
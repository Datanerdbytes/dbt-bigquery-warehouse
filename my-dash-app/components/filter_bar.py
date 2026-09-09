import dash
from dash import html, dcc
import dash_bootstrap_components as dbc

def create_filter_bar(
    df_merged,
    date_picker_id,
    category_dropdown_id,
    country_dropdown_id
):
    # Detect category and country columns dynamically
    cat_col = next((c for c in ["category_name", "category", "product_category", "Category"] if c in df_merged.columns), None)
    country_col = next((c for c in ["country", "region", "Country", "Region"] if c in df_merged.columns), None)

    # Build options
    category_options = [{"label": "All Categories", "value": "ALL"}]
    if cat_col:
        category_options += [{"label": str(cat), "value": str(cat)} for cat in sorted(df_merged[cat_col].dropna().unique())]

    country_options = [{"label": "All Countries", "value": "ALL"}]
    if country_col:
        country_options += [{"label": str(country), "value": str(country)} for country in sorted(df_merged[country_col].dropna().unique())]

    # Date range boundaries
    date_col = next((c for c in ["order_date", "OrderDate", "date"] if c in df_merged.columns), df_merged.columns[0])
    min_date = df_merged[date_col].min()
    max_date = df_merged[date_col].max()

    return html.Div(
        dbc.Row(
            dbc.Col(
                html.Div(
                    dbc.Row(
                        [
                            dbc.Col(
                                html.Div(
                                    [
                                        html.Label("Date Range", className="text-muted small fw-bold mb-1 d-block"),
                                        dcc.DatePickerRange(
                                            id=date_picker_id,
                                            min_date_allowed=min_date,
                                            max_date_allowed=max_date,
                                            initial_visible_month=min_date,
                                            start_date=min_date,
                                            end_date=max_date,
                                            display_format="YYYY-MM-DD",
                                            className="w-100"
                                        )
                                    ]
                                ),
                                width=12, md=4
                            ),
                            dbc.Col(
                                html.Div(
                                    [
                                        html.Label("Product Category", className="text-muted small fw-bold mb-1 d-block"),
                                        dcc.Dropdown(
                                            id=category_dropdown_id,
                                            options=category_options,
                                            value="ALL",
                                            clearable=False,
                                            className="dark-dropdown w-100"
                                        )
                                    ]
                                ),
                                width=12, md=4
                            ),
                            dbc.Col(
                                html.Div(
                                    [
                                        html.Label("Region", className="text-muted small fw-bold mb-1 d-block"),
                                        dcc.Dropdown(
                                            id=country_dropdown_id,
                                            options=country_options,
                                            value="ALL",
                                            clearable=False,
                                            className="dark-dropdown w-100"
                                        )
                                    ]
                                ),
                                width=12, md=4
                            )
                        ],
                        className="g-3 align-items-center"
                    ),
                    className="dark-card px-4 py-3 rounded shadow-sm"
                ),
                width=12
            ),
            className="mb-0"
        ),
        className="sticky-filter-bar"
    )
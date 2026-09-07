import dash
from dash import html, dcc
import dash_bootstrap_components as dbc

def create_filter_bar(df_merged):
    # Detect the correct category column name dynamically
    cat_col = next((c for c in ["category_name", "category", "product_category", "Category"] if c in df_merged.columns), None)
    country_col = next((c for c in ["country", "region", "Country", "Region"] if c in df_merged.columns), None)

    # Build Category Options safely
    if cat_col:
        category_options = [{"label": "All Categories", "value": "ALL"}] + [
            {"label": str(cat), "value": str(cat)} for cat in sorted(df_merged[cat_col].dropna().unique())
        ]
    else:
        category_options = [{"label": "All Categories", "value": "ALL"}]

    # Build Region Options safely
    if country_col:
        country_options = [{"label": "All Countries", "value": "ALL"}] + [
            {"label": str(country), "value": str(country)} for country in sorted(df_merged[country_col].dropna().unique())
        ]
    else:
        country_options = [{"label": "All Countries", "value": "ALL"}]

    # Default Date Range Boundaries
    date_col = next((c for c in ["order_date", "OrderDate", "date"] if c in df_merged.columns), df_merged.columns[0])
    min_date = df_merged[date_col].min()
    max_date = df_merged[date_col].max()

    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Label("Date Range", className="text-muted small fw-bold mb-1 d-block"),
                            dcc.DatePickerRange(
                                id="date-picker-range",
                                min_date_allowed=min_date,
                                max_date_allowed=max_date,
                                initial_visible_month=min_date,
                                start_date=min_date,
                                end_date=max_date,
                                display_format="YYYY-MM-DD",
                                className="w-100"
                            )
                        ],
                        width=12, md=4
                    ),
                    dbc.Col(
                        [
                            html.Label("Product Category", className="text-muted small fw-bold mb-1 d-block"),
                            dcc.Dropdown(
                                id="category-dropdown",
                                options=category_options,
                                value="ALL",
                                clearable=False,
                                className="dark-dropdown"
                            )
                        ],
                        width=12, md=4
                    ),
                    dbc.Col(
                        [
                            html.Label("Region", className="text-muted small fw-bold mb-1 d-block"),
                            dcc.Dropdown(
                                id="country-dropdown",
                                options=country_options,
                                value="ALL",
                                clearable=False,
                                className="dark-dropdown"
                            )
                        ],
                        width=12, md=4
                    )
                ],
                className="g-3"
            )
        ],
        className="dark-card p-3 rounded shadow-sm sticky-filter-bar mb-4"
    )
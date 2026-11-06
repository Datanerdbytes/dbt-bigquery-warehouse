import pandas as pd
from dash import dcc, html


def create_filter_bar(
    df_merged, date_picker_id, category_dropdown_id, country_dropdown_id
):
    # A bar built without the dataset must not select a date window: the
    # selected range is published to the shared filter store, and a window that
    # lies outside the dataset renders the dashboard empty.
    min_date_allowed = "2023-01-01"
    max_date_allowed = "2026-12-31"
    default_start_date = None
    default_end_date = None
    visible_month = min_date_allowed
    category_options = [{"label": "All Categories", "value": "ALL"}]
    country_options = [{"label": "All Countries", "value": "ALL"}]

    if df_merged is not None and not df_merged.empty:
        # Detect category and country columns dynamically
        cat_col = next(
            (
                c
                for c in ["category_name", "category", "product_category", "Category"]
                if c in df_merged.columns
            ),
            None,
        )
        country_col = next(
            (
                c
                for c in ["country", "region", "Country", "Region"]
                if c in df_merged.columns
            ),
            None,
        )

        # Build options
        if cat_col:
            category_options += [
                {"label": str(cat), "value": str(cat)}
                for cat in sorted(df_merged[cat_col].dropna().unique())
            ]

        if country_col:
            country_options += [
                {"label": str(country), "value": str(country)}
                for country in sorted(df_merged[country_col].dropna().unique())
            ]

        # Date range boundaries across entire dataset
        date_col = next(
            (c for c in ["order_date", "OrderDate", "date"] if c in df_merged.columns),
            df_merged.columns[0] if len(df_merged.columns) > 0 else None,
        )

        if date_col and date_col in df_merged.columns:
            dates = pd.to_datetime(df_merged[date_col].dropna())
            if not dates.empty:
                min_date_allowed = dates.min().strftime("%Y-%m-%d")
                max_date_allowed = dates.max().strftime("%Y-%m-%d")
                latest_year = dates.dt.year.max()
                latest_year_dates = dates[dates.dt.year == latest_year]
                default_start_date = latest_year_dates.min().strftime("%Y-%m-%d")
                default_end_date = latest_year_dates.max().strftime("%Y-%m-%d")
                visible_month = default_start_date

    return html.Div(
        [
            html.Div(
                [
                    html.Label(
                        "Date range", htmlFor=date_picker_id, className="filter-label"
                    ),
                    dcc.DatePickerRange(
                        id=date_picker_id,
                        min_date_allowed=min_date_allowed,
                        max_date_allowed=max_date_allowed,
                        initial_visible_month=visible_month,
                        start_date=default_start_date,
                        end_date=default_end_date,
                        display_format="YYYY-MM-DD",
                        className="dashboard-date-picker",
                    ),
                ],
                className="filter-field filter-dates",
            ),
            html.Div(
                [
                    html.Label(
                        "Product category",
                        htmlFor=category_dropdown_id,
                        className="filter-label",
                    ),
                    dcc.Dropdown(
                        id=category_dropdown_id,
                        options=category_options,
                        value="ALL",
                        clearable=False,
                        className="dashboard-dropdown",
                    ),
                ],
                className="filter-field",
            ),
            html.Div(
                [
                    html.Label(
                        "Country", htmlFor=country_dropdown_id, className="filter-label"
                    ),
                    dcc.Dropdown(
                        id=country_dropdown_id,
                        options=country_options,
                        value="ALL",
                        clearable=False,
                        className="dashboard-dropdown",
                    ),
                ],
                className="filter-field",
            ),
        ],
        className="dashboard-filters",
    )

"""Presentation and geographic aggregation for the overview revenue pilot."""

import pandas as pd
import plotly.express as px
import pycountry
from dash import html
import dash_bootstrap_components as dbc
from theme import COLORS, style_figure


def normalize_view(value):
    return "map" if value == "map" else "donut"


def revenue_menu():
    return dbc.DropdownMenu(
        [
            dbc.DropdownMenuItem("Replace chart", header=True),
            dbc.DropdownMenuItem(
                "Donut · Category", id="overview-revenue-donut", active=True
            ),
            dbc.DropdownMenuItem("Map · Country", id="overview-revenue-map"),
        ],
        label=[
            html.Span("⋮", **{"aria-hidden": "true"}),
            html.Span("Replace revenue chart", className="visually-hidden"),
        ],
        toggle_class_name="revenue-chart-toggle",
        className="revenue-chart-menu",
        align_end=True,
        caret=False,
        id="overview-revenue-menu",
    )


def country_code(value):
    if pd.isna(value) or not str(value).strip():
        return None
    name = str(value).strip()
    aliases = {"uk": "GBR", "south korea": "KOR", "russia": "RUS"}
    try:
        return pycountry.countries.lookup(aliases.get(name.casefold(), name)).alpha_3
    except LookupError:
        return None


def aggregate_countries(frame):
    """Combine aliases before plotting; retain unknown revenue for disclosure."""
    data = frame.reindex(columns=["country", "gross_sales_amount"]).copy()
    data["iso3"] = data["country"].map(country_code)
    data["gross_sales_amount"] = pd.to_numeric(
        data["gross_sales_amount"], errors="coerce"
    ).fillna(0)
    missing = data["iso3"].isna()
    unknown_revenue = data.loc[missing, "gross_sales_amount"].sum()
    grouped = (
        data.loc[~missing].groupby("iso3", as_index=False)["gross_sales_amount"].sum()
    )
    grouped["country"] = grouped["iso3"].map(
        lambda code: pycountry.countries.get(alpha_3=code).name
    )
    return (
        grouped.sort_values("gross_sales_amount", ascending=False),
        float(unknown_revenue),
        bool(missing.any()),
    )


def map_figure(frame):
    countries, unknown_revenue, has_unknown = aggregate_countries(frame)
    if countries.empty:
        figure = style_figure(
            px.scatter(title="No geographic data for selected period")
        )
    else:
        figure = style_figure(
            px.choropleth(
                countries,
                locations="iso3",
                locationmode="ISO-3",
                color="gross_sales_amount",
                hover_name="country",
                custom_data=["country"],
                projection="natural earth",
                color_continuous_scale=[COLORS["raised"], COLORS["accent"]],
                range_color=(
                    min(0, float(countries["gross_sales_amount"].min())),
                    max(1, float(countries["gross_sales_amount"].max())),
                ),
                labels={"gross_sales_amount": "Revenue"},
            )
        )
        figure.update_traces(
            hovertemplate="<b>%{customdata[0]}</b><br>Revenue: $%{z:,.0f}<extra></extra>",
            marker_line_color=COLORS["border"],
            marker_line_width=0.5,
        )
        figure.update_geos(
            center={"lon": 0, "lat": 10},
            projection_rotation={"lon": 0, "lat": 0, "roll": 0},
            projection_scale=1,
            lonaxis_range=[-180, 180],
            lataxis_range=[-60, 85],
            showframe=False,
            showcoastlines=False,
            showcountries=True,
            countrycolor=COLORS["border"],
            showland=True,
            landcolor=COLORS["raised"],
            bgcolor=COLORS["surface"],
        )
        figure.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            coloraxis_colorbar=dict(
                orientation="h",
                thickness=8,
                len=0.85,
                y=0,
                yanchor="top",
                tickprefix="$",
                tickformat="~s",
            ),
        )
    rows = [
        html.Tr(
            [
                html.Th(row.country, scope="row"),
                html.Td(f"${row.gross_sales_amount:,.0f}"),
            ]
        )
        for row in countries.itertuples()
    ]
    if has_unknown:
        rows.append(
            html.Tr(
                [
                    html.Th("Missing or unrecognized country", scope="row"),
                    html.Td(f"${unknown_revenue:,.0f}"),
                ]
            )
        )
    details = [
        (
            html.P(
                f"${unknown_revenue:,.0f} revenue is not mapped because its country is missing or unrecognized.",
                className="panel-description",
                role="status",
            )
            if has_unknown
            else None
        ),
        (
            html.Details(
                [
                    html.Summary("View country revenue"),
                    html.Table(
                        [
                            html.Caption(
                                "Revenue by country for the selected filters",
                                className="visually-hidden",
                            ),
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("Country", scope="col"),
                                        html.Th("Revenue", scope="col"),
                                    ]
                                )
                            ),
                            html.Tbody(rows),
                        ],
                        className="revenue-country-table",
                    ),
                ],
                className="revenue-country-details",
            )
            if rows
            else None
        ),
    ]
    return figure, details
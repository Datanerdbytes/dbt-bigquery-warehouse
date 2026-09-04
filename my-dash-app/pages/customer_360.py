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
    className="dashboard-container",
    children=[
        dbc.Container(
            [
                # Row 1: Header Banner
                dbc.Row(
                    dbc.Col(
                        html.Div(
                            [
                                html.H2("Customer 360 Dashboard", className="fw-bold mb-0 text-white"),
                                html.P(
                                    "Customer Lifetime Value, Purchase Patterns, and Behavioral Segmentation",
                                    className="mb-0 text-white-50 small",
                                )
                            ],
                            className="header-banner p-2 mb-2 bg-dark rounded"
                        ),
                        width=12
                    )
                ),

                # Row 2: Filter Control Bar
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
                    )
                ),

                # Row 3: Customer KPI Summary Cards
                dbc.Row(
                    [
                        # Total Active Customers
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
                        # Avg Customer Lifetime Value (CLV / Spend)
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
                        # Avg Purchase Frequency
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
                        # Repeat Customer Rate %
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

                # Row 4: Visuals Placeholder Container
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
                )
            ],
            fluid=False
        )
    ]
)
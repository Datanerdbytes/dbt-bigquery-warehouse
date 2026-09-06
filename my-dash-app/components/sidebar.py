import dash
from dash import html
import dash_bootstrap_components as dbc

def create_sidebar():
    return html.Div(
        className="sidebar-container d-flex flex-column p-3 text-white",
        children=[
            # 1. Brand Logo & Header
            html.Div(
                [
                    html.Div(className="brand-icon me-2 shadow-sm"),
                    html.H4("Dashdark X", className="fw-bold mb-0 text-white fs-5"),
                ],
                className="d-flex align-items-center mb-4 px-2 pt-2"
            ),

            # 2. Search Bar
            html.Div(
                [
                    dbc.Input(
                        type="search",
                        placeholder="Search for...",
                        className="sidebar-search-input py-2 px-3 rounded-3",
                    )
                ],
                className="mb-4"
            ),

            # 3. Navigation Links
            html.Div(
                [
                    html.Div("Dashboard", className="text-muted text-uppercase fw-bold small px-2 mb-2 fs-7"),
                    dbc.Nav(
                        [
                            dbc.NavLink(
                                [
                                    html.I(className="bi bi-grid-fill me-3"),
                                    html.Span("Product Overview")
                                ],
                                href="/",
                                active="exact",
                                className="sidebar-link rounded-3 px-3 py-2 mb-1 d-flex align-items-center"
                            ),
                            dbc.NavLink(
                                [
                                    html.I(className="bi bi-people-fill me-3"),
                                    html.Span("Customer 360")
                                ],
                                href="/customers",
                                active="exact",
                                className="sidebar-link rounded-3 px-3 py-2 mb-1 d-flex align-items-center"
                            ),
                        ],
                        vertical=True,
                        pills=True,
                    ),
                ],
                className="mb-4"
            ),

            # 4. Secondary Menu Placeholders
            html.Div(
                [
                    html.Div("Manage", className="text-muted text-uppercase fw-bold small px-2 mb-2 fs-7"),
                    dbc.Nav(
                        [
                            html.A(
                                [
                                    html.Div([html.I(className="bi bi-box-seam me-3"), html.Span("Products")], className="d-flex align-items-center"),
                                    html.I(className="bi bi-chevron-right small text-muted")
                                ],
                                href="#",
                                className="sidebar-link rounded-3 px-3 py-2 mb-1 d-flex align-items-center justify-content-between"
                            ),
                            html.A(
                                [
                                    html.Div([html.I(className="bi bi-gear me-3"), html.Span("Settings")], className="d-flex align-items-center"),
                                    html.I(className="bi bi-chevron-right small text-muted")
                                ],
                                href="#",
                                className="sidebar-link rounded-3 px-3 py-2 mb-1 d-flex align-items-center justify-content-between"
                            ),
                        ],
                        vertical=True
                    )
                ],
                className="mb-4"
            ),

            # 5. Bottom User Profile Card
            html.Div(
                [
                    html.Hr(className="border-secondary my-3"),
                    html.Div(
                        [
                            html.Div(
                                "JC",
                                className="avatar-circle text-white fw-bold d-flex align-items-center justify-content-center me-3"
                            ),
                            html.Div(
                                [
                                    html.Div("John Carter", className="fw-bold small text-white lh-1"),
                                    html.Small("Account settings", className="text-muted fs-7")
                                ]
                            )
                        ],
                        className="d-flex align-items-center px-2 py-1"
                    )
                ],
                className="mt-auto"
            )
        ]
    )
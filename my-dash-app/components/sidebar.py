import dash
from dash import html
import dash_bootstrap_components as dbc

def create_sidebar():
    return html.Div(
        className="sidebar-container d-flex flex-column p-3 text-white",
        children=[
            # 1. Brand Logo, Title & Toggle Button
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(className="brand-icon me-2 shadow-sm flex-shrink-0"),
                            html.H4("Dashdark X", className="fw-bold mb-0 text-white fs-5 sidebar-brand-text"),
                        ],
                        className="d-flex align-items-center sidebar-brand-wrapper"
                    ),
                    dbc.Button(
                        html.I(className="bi bi-list fs-5"),
                        id="sidebar-toggle-btn",
                        color="dark",
                        className="border-secondary text-white rounded-3 flex-shrink-0 p-1 sidebar-toggle-btn",
                        style={"backgroundColor": "transparent"},
                        title="Toggle Sidebar"
                    )

                ],
                className="d-flex align-items-center justify-content-between mb-4 px-1 pt-2 sidebar-header-row"
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
                className="mb-4 sidebar-collapse-item"
            ),

            # 3. Navigation Links
            html.Div(
                [
                    html.Div("Dashboard", className="text-muted text-uppercase fw-bold small px-2 mb-2 fs-7 sidebar-collapse-item"),
                    dbc.Nav(
                        [
                            dbc.NavLink(
                                [
                                    html.I(className="bi bi-grid-fill me-3 sidebar-icon", title="Product Overview"),
                                    html.Span("Product Overview", className="sidebar-link-text")
                                ],
                                href="/",
                                active="exact",
                                className="sidebar-link rounded-3 px-3 py-2 mb-1 d-flex align-items-center"
                            ),
                            dbc.NavLink(
                                [
                                    html.I(className="bi bi-people-fill me-3 sidebar-icon", title="Customer 360"),
                                    html.Span("Customer 360", className="sidebar-link-text")
                                ],
                                href="/customers",
                                active="exact",
                                className="sidebar-link rounded-3 px-3 py-2 mb-1 d-flex align-items-center"
                            ),
                            dbc.NavLink(
                                [
                                    html.I(className="bi bi-activity me-3 sidebar-icon", title="Pipeline Health"),
                                    html.Span("Pipeline Health", className="sidebar-link-text")
                                ],
                                href="/pipeline-health",
                                active="exact",
                                className="sidebar-link rounded-3 px-3 py-2 mb-1 d-flex align-items-center"
                            )
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
                    html.Div("Manage", className="text-muted text-uppercase fw-bold small px-2 mb-2 fs-7 sidebar-collapse-item"),
                    dbc.Nav(
                        [
                            html.A(
                                [
                                    html.Div([html.I(className="bi bi-box-seam me-3 sidebar-icon"), html.Span("Products", className="sidebar-link-text")], className="d-flex align-items-center sidebar-link-inner"),
                                    html.I(className="bi bi-chevron-right small text-muted sidebar-link-text")
                                ],
                                href="#",
                                className="sidebar-link rounded-3 px-3 py-2 mb-1 d-flex align-items-center justify-content-between",
                                title="Products"
                            ),
                            html.A(
                                [
                                    html.Div([html.I(className="bi bi-gear me-3 sidebar-icon"), html.Span("Settings", className="sidebar-link-text")], className="d-flex align-items-center sidebar-link-inner"),
                                    html.I(className="bi bi-chevron-right small text-muted sidebar-link-text")
                                ],
                                href="#",
                                className="sidebar-link rounded-3 px-3 py-2 mb-1 d-flex align-items-center justify-content-between",
                                title="Settings"
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
                    html.Hr(className="border-secondary my-3 sidebar-collapse-item"),
                    html.Div(
                        [
                            html.Div(
                                "JC",
                                className="avatar-circle text-white fw-bold d-flex align-items-center justify-content-center me-3 sidebar-avatar flex-shrink-0"
                            ),
                            html.Div(
                                [
                                    html.Div("John Carter", className="fw-bold small text-white lh-1 sidebar-link-text text-nowrap"),
                                    html.Small("Account settings", className="text-muted fs-7 sidebar-link-text text-nowrap")
                                ]
                            )
                        ],
                        className="d-flex align-items-center px-2 py-1 sidebar-user-row"
                    )
                ],
                className="mt-auto"
            )
        ]
    )
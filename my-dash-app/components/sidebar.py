from dash import html
import dash_bootstrap_components as dbc


def create_sidebar():
    links = [
        ("Product Overview", "/dashboard", "bi-graph-up"),
        ("Customer 360", "/customers", "bi-people"),
        ("Pipeline Health", "/pipeline-health", "bi-activity"),
    ]
    return html.Aside(
        [
            html.Div(
                [
                    html.Div(
                        [html.Strong("Quantum Echo"), html.Span("Analytics workspace")],
                        className="sidebar-brand",
                    ),
                    html.Button(
                        html.I(className="bi bi-list", **{"aria-hidden": "true"}),
                        id="sidebar-toggle-btn",
                        className="sidebar-toggle-btn",
                        title="Toggle navigation",
                        **{
                            "aria-label": "Toggle navigation",
                            "aria-expanded": "true",
                            "aria-controls": "dashboard-navigation",
                        },
                    ),
                ],
                className="sidebar-heading",
            ),
            dbc.Nav(
                [
                    dbc.NavLink(
                        [
                            html.I(className=f"bi {icon}", **{"aria-hidden": "true"}),
                            html.Span(label, className="sidebar-link-text"),
                        ],
                        href=href,
                        active="exact",
                        className="sidebar-link",
                    )
                    for label, href, icon in links
                ],
                id="dashboard-navigation",
                className="sidebar-navigation",
                vertical=True,
            ),
            html.Button(
                "Sign out", id="dashboard-signout", className="auth-signout-button"
            ),
            html.Div(
                [
                    html.I(className="bi bi-database", **{"aria-hidden": "true"}),
                    html.Span("Data analytics", className="sidebar-link-text"),
                ],
                className="sidebar-footer",
            ),
        ],
        className="sidebar-container",
        **{"aria-label": "Main navigation"},
    )

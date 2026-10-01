from dash import html
from flask import g, has_request_context
import dash_bootstrap_components as dbc


def create_account_menu():
    user = getattr(g, "auth_user", {}) if has_request_context() else {}
    metadata = user.get("user_metadata") or {}
    email = user.get("email") or ""
    name = str(
        metadata.get("username")
        or metadata.get("full_name")
        or metadata.get("name")
        or email.split("@")[0]
        or "Account"
    )
    initials = "".join(part[0] for part in name.split()[:2]).upper()

    def identity():
        return [
            html.Span(
                initials,
                className="sidebar-account-avatar",
                **{"aria-hidden": "true"},
            ),
            html.Span(
                [html.Strong(name), html.Span("Analytics workspace")],
                className="sidebar-account-identity",
            ),
        ]

    return html.Details(
        [
            html.Summary(
                identity()
                + [html.I(className="bi bi-three-dots", **{"aria-hidden": "true"})],
                className="sidebar-account-trigger",
                **{"aria-label": f"Account options for {name}"},
            ),
            html.Div(
                [
                    html.Div(identity(), className="sidebar-account-heading"),
                    html.Div(email, className="sidebar-account-email"),
                    html.Hr(),
                    html.Button(
                        [
                            html.I(
                                className="bi bi-box-arrow-right",
                                **{"aria-hidden": "true"},
                            ),
                            "Log out",
                        ],
                        id="dashboard-signout",
                        className="sidebar-account-action",
                    ),
                ],
                className="sidebar-account-panel",
                **{"aria-label": "Account options"},
            ),
        ],
        id="sidebar-account",
        className="sidebar-account",
    )


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
            create_account_menu(),
        ],
        className="sidebar-container",
        **{"aria-label": "Main navigation"},
    )

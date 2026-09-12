import dash
from dash import html, dcc
import dash_bootstrap_components as dbc

def create_header():
    # Sample notification items
    notification_items = [
        dbc.DropdownMenuItem(
            [
                html.Div("Data Sync Complete", className="fw-bold text-white small"),
                html.Div("BigQuery Gold tables updated 15m ago.", className="text-muted fs-7"),
            ],
            className="py-2 border-bottom border-secondary"
        ),
        dbc.DropdownMenuItem(
            [
                html.Div("Revenue Spike Alert 📈", className="fw-bold text-success small"),
                html.Div("Bikes category saw +12% increase yesterday.", className="text-muted fs-7"),
            ],
            className="py-2 border-bottom border-secondary"
        ),
        dbc.DropdownMenuItem(
            [
                html.Div("System Maintenance", className="fw-bold text-warning small"),
                html.Div("Scheduled pipeline update at 02:00 UTC.", className="text-muted fs-7"),
            ],
            className="py-2"
        ),
    ]

    return html.Div(
        className="top-header-bar d-flex align-items-center justify-content-between px-4 py-3 mb-4 rounded-3 position-relative z-3",
        children=[
            # Left: Welcome Greeting & Title Context
            html.Div(
                [
                    html.H4("Welcome back, John! 👋", className="text-white fw-bold mb-1 fs-5"),
                    html.P("Here's an overview of your store's latest performance.", className="text-muted small mb-0 fs-7")
                ]
            ),

            # Right: Action Group
            html.Div(
                [
                    # Notification Dropdown
                    dbc.DropdownMenu(
                        label=html.Div(
                            [
                                html.I(className="bi bi-bell-fill fs-6 text-muted"),
                                html.Span(className="position-absolute top-0 start-100 translate-middle p-1 bg-danger border border-light rounded-circle")
                            ],
                            className="position-relative d-inline-flex align-items-center justify-content-center"
                        ),
                        children=notification_items,
                        nav=False,
                        in_navbar=False,
                        menu_variant="dark",
                        toggleClassName="px-2 py-1 shadow-none border-0 bg-transparent",
                        className="me-3 header-icon-btn rounded-3 border border-secondary d-flex align-items-center justify-content-center",
                        align_end=True
                    ),
                    
                    # Export Preview Trigger Button
                    dbc.Button(
                        [
                            html.I(className="bi bi-file-earmark-text me-2"),
                            html.Span("Preview & Export")
                        ],
                        id="global-export-btn",
                        color="primary",
                        className="export-btn rounded-3 px-3 py-2 fw-semibold border-0 ms-1"
                    ),
                    
                    # Download component
                    dcc.Download(id="global-download-file")
                ],
                className="d-flex align-items-center"
            ),

            # Executive Summary Preview Modal
            dbc.Modal(
                [
                    dbc.ModalHeader(
                        dbc.ModalTitle("Executive Report Preview", className="fw-bold text-white"),
                        close_button=True
                    ),
                    dbc.ModalBody(
                        html.Div(id="export-modal-body-content"),
                        style={"maxHeight": "70vh", "overflowY": "auto"}
                    ),
                    dbc.ModalFooter(
                        [
                            dbc.Button("Cancel", id="close-export-modal-btn", color="secondary", outline=True, className="me-2"),
                            dbc.Button(
                                [
                                    html.I(className="bi bi-download me-2"),
                                    html.Span("Download CSV Report")
                                ],
                                id="confirm-download-btn",
                                color="success",
                                className="fw-semibold"
                            )
                        ]
                    )
                ],
                id="export-preview-modal",
                size="xl",
                is_open=False,
                centered=True
            )
        ]
    )
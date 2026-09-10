import dash
from dash import html, dcc
import dash_bootstrap_components as dbc

def create_header():
    return html.Div(
        className="top-header-bar d-flex align-items-center justify-content-between px-4 py-3 mb-4 rounded-3",
        children=[
            # Left: Welcome Greeting & Title Context
            html.Div(
                [
                    html.H4("Welcome back, John! 👋", className="text-white fw-bold mb-1 fs-5"),
                    html.P("Here's an overview of your store's latest performance.", className="text-muted small mb-0 fs-7")
                ]
            ),

            # Right: Action Group (Notification & Export Button)
            html.Div(
                [
                    # Notification Icon Button
                    dbc.Button(
                        html.I(className="bi bi-bell-fill fs-6 text-muted"),
                        color="dark",
                        outline=True,
                        className="me-2 header-icon-btn rounded-3 border-secondary d-flex align-items-center justify-content-center p-2"
                    ),
                    
                    # Export Preview Trigger Button
                    dbc.Button(
                        [
                            html.I(className="bi bi-file-earmark-text me-2"),
                            html.Span("Preview & Export")
                        ],
                        id="global-export-btn",
                        color="primary",
                        className="export-btn rounded-3 px-3 py-2 fw-semibold border-0"
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
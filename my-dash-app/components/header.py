import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
from data_loader import load_pipeline_health_summary

def create_header():
    # Fetch real-time health metrics from audit schema
    df_summary = load_pipeline_health_summary()

    # Extract dynamic metrics with safe fallbacks
    if not df_summary.empty:
        status = df_summary["overall_system_status"].iloc[0]
        failed_count = int(df_summary["failed_tests"].iloc[0])
        warning_count = int(df_summary["warning_tests"].iloc[0])
        passed_count = int(df_summary["passed_tests"].iloc[0])
        stale_count = int(df_summary["stale_tables_count"].iloc[0]) if "stale_tables_count" in df_summary.columns else 0
        last_check = str(df_summary["last_dbt_run"].iloc[0]) if "last_dbt_run" in df_summary.columns else "Recently"
    else:
        status, failed_count, warning_count, passed_count, stale_count, last_check = "HEALTHY", 0, 0, 0, 0, "N/A"

    # Notification Panel Items List
    notification_items = [
        # Panel Title Header
        html.Div(
            [
                html.Span("Notifications", className="fw-bold text-white fs-6"),
                html.Span(
                    f"{failed_count + warning_count} alert(s)",
                    className="badge bg-warning text-dark ms-2" if warning_count > 0 else "badge bg-secondary ms-2"
                )
            ],
            className="d-flex align-items-center justify-content-between px-3 py-2 border-bottom border-secondary mb-1"
        )
    ]

    # 1. Critical Failure Notifications
    if failed_count > 0:
        notification_items.append(
            dbc.DropdownMenuItem(
                [
                    html.Div(f"🚨 {failed_count} dbt Test Failures Detected", className="fw-bold text-danger small mb-1"),
                    html.Div("Immediate attention required in BigQuery tables.", className="text-muted fs-7"),
                ],
                className="px-3 py-2 border-bottom border-secondary",
                href="/pipeline-health"
            )
        )

    # 2. Warning Notifications
    if warning_count > 0 or status == "WARNING":
        notification_items.append(
            dbc.DropdownMenuItem(
                [
                    html.Div("⚠️ Pipeline Warning Active", className="fw-bold text-warning small mb-1"),
                    html.Div(f"{warning_count} assertion warnings recorded.", className="text-muted fs-7"),
                ],
                className="px-3 py-2 border-bottom border-secondary",
                href="/pipeline-health"
            )
        )

    # 3. Data Freshness Status
    if stale_count > 0:
        notification_items.append(
            dbc.DropdownMenuItem(
                [
                    html.Div("🕒 Stale Data Tables Found", className="fw-bold text-warning small mb-1"),
                    html.Div(f"{stale_count} ingestion targets exceeded latency threshold.", className="text-muted fs-7"),
                ],
                className="px-3 py-2 border-bottom border-secondary",
                href="/pipeline-health"
            )
        )
    else:
        notification_items.append(
            dbc.DropdownMenuItem(
                [
                    html.Div("✅ Data Ingestion Healthy", className="fw-bold text-success small mb-1"),
                    html.Div(f"All BigQuery tables updated on schedule ({passed_count} tests passed).", className="text-muted fs-7"),
                ],
                className="px-3 py-2 border-bottom border-secondary"
            )
        )

    # 4. General Log Info
    notification_items.append(
        dbc.DropdownMenuItem(
            [
                html.Div("System Observability Active", className="fw-bold text-white small mb-1"),
                html.Div(f"Last pipeline run: {last_check[:19] if len(last_check) > 19 else last_check}", className="text-muted fs-7"),
            ],
            className="px-3 py-2"
        )
    )

    # Red notification dot visibility
    has_active_alerts = failed_count > 0 or warning_count > 0 or status != "HEALTHY"

    return html.Div(
        className="top-header-bar d-flex align-items-center justify-content-between px-4 py-3 mb-4 rounded-3",
        children=[
            # Left: Welcome Greeting & Context
            html.Div(
                [
                    html.H4("Welcome back, John! 👋", className="text-white fw-bold mb-1 fs-5"),
                    html.P("Here's an overview of your store's latest performance and pipeline observability.", className="text-muted small mb-0 fs-7")
                ]
            ),

            # Right: Notification Dropdown & Action Button
            html.Div(
                [
                    # Dynamic Notification Bell
                    dbc.DropdownMenu(
                        label=html.Div(
                            [
                                html.I(className="bi bi-bell-fill fs-6 text-muted"),
                                html.Span(
                                    className="position-absolute top-0 start-100 translate-middle p-1 bg-danger border border-light rounded-circle"
                                ) if has_active_alerts else None
                            ],
                            className="position-relative d-inline-block"
                        ),
                        children=[
                            html.Div(
                                notification_items,
                                className="dark-card shadow-lg border border-secondary p-2 rounded",
                                style={"minWidth": "320px"}
                            )
                        ],
                        nav=False,
                        in_navbar=False,
                        toggle_style={"backgroundColor": "transparent", "border": "1px solid #6c757d", "padding": "0.5rem 0.75rem"},
                        className="me-2 header-icon-btn rounded-3",
                        align_end=True
                    ),
                    
                    # Report Modal Trigger Button
                    dbc.Button(
                        [
                            html.I(className="bi bi-file-earmark-text me-2"),
                            html.Span("Preview & Export")
                        ],
                        id="global-export-btn",
                        color="primary",
                        className="export-btn rounded-3 px-3 py-2 fw-semibold border-0"
                    ),
                    
                    dcc.Download(id="global-download-file")
                ],
                className="d-flex align-items-center"
            ),

            # Executive Report Preview Modal
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
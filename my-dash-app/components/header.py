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

    # Build dynamic notification menu items
    notification_items = []

    if failed_count > 0:
        notification_items.append(
            dbc.DropdownMenuItem(
                [
                    html.Div(f"🚨 {failed_count} dbt Test Failures Detected", className="fw-bold text-danger small"),
                    html.Div("Immediate attention required in BigQuery tables.", className="text-muted fs-7"),
                ],
                className="py-2 border-bottom border-secondary",
                href="/pipeline-health"
            )
        )

    if warning_count > 0 or status == "WARNING":
        notification_items.append(
            dbc.DropdownMenuItem(
                [
                    html.Div("⚠️ Pipeline Warning Active", className="fw-bold text-warning small"),
                    html.Div(f"{warning_count} assertion warnings recorded.", className="text-muted fs-7"),
                ],
                className="py-2 border-bottom border-secondary",
                href="/pipeline-health"
            )
        )

    if stale_count > 0:
        notification_items.append(
            dbc.DropdownMenuItem(
                [
                    html.Div("🕒 Stale Data Tables Found", className="fw-bold text-warning small"),
                    html.Div(f"{stale_count} ingestion targets exceeded latency threshold.", className="text-muted fs-7"),
                ],
                className="py-2 border-bottom border-secondary",
                href="/pipeline-health"
            )
        )
    else:
        notification_items.append(
            dbc.DropdownMenuItem(
                [
                    html.Div("✅ Data Ingestion Healthy", className="fw-bold text-success small"),
                    html.Div(f"All BigQuery tables updated on schedule ({passed_count} tests passed).", className="text-muted fs-7"),
                ],
                className="py-2 border-bottom border-secondary"
            )
        )

    notification_items.append(
        dbc.DropdownMenuItem(
            [
                html.Div("System Observability Active", className="fw-bold text-white small"),
                html.Div(f"Last pipeline run: {last_check[:19] if len(last_check) > 19 else last_check}", className="text-muted fs-7"),
            ],
            className="py-2"
        )
    )

    has_active_alerts = failed_count > 0 or warning_count > 0 or status != "HEALTHY"

    # Configure Alert Toast details based on current health status
    toast_header = "🚨 Critical Pipeline Failure" if failed_count > 0 else "⚠️ Pipeline Warning Alert"
    toast_icon = "danger" if failed_count > 0 else "warning"
    toast_message = (
        f"Detected {failed_count} failing dbt assertion(s) in BigQuery."
        if failed_count > 0
        else f"Pipeline completed with {warning_count} warning assertion(s)."
    )

    return html.Div(
        className="top-header-bar d-flex align-items-center justify-content-between px-4 py-3 mb-4 rounded-3 position-relative",
        children=[
            # Left: Welcome Greeting
            html.Div(
                [
                    html.H4("Welcome back, Roel! 👋", className="text-white fw-bold mb-1 fs-5"),
                    html.P("Here's an overview of your store's latest performance and pipeline observability.", className="text-muted small mb-0 fs-7")
                ]
            ),

            # Right: Notification Bell & Action Buttons
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
                                className="dark-card shadow-lg border border-secondary p-1 rounded"
                            )
                        ],
                        nav=False,
                        in_navbar=False,
                        toggle_style={"backgroundColor": "transparent", "border": "1px solid #6c757d", "padding": "0.5rem 0.75rem"},
                        className="me-2 header-icon-btn rounded-3",
                        align_end=True
                    ),
                    
                    # Report Modal Trigger
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

            # Ingestion Alert Toast Container (Positioned top-right)
            dbc.Toast(
                [
                    html.P(toast_message, className="mb-1 text-white small"),
                    html.A("View Details in Pipeline Health →", href="/pipeline-health", className="text-info small fw-bold text-decoration-none")
                ],
                id="pipeline-alert-toast",
                header=toast_header,
                icon=toast_icon,
                is_open=has_active_alerts,  # Opens automatically if alerts exist
                dismissable=True,
                duration=8000,  # Auto-dismisses after 8 seconds
                style={"position": "fixed", "top": "20px", "right": "20px", "zIndex": 9999, "minWidth": "320px"},
                className="dark-card border border-secondary shadow-lg"
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
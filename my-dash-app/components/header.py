import logging

from dash import html, dcc, callback, Input, Output, State, no_update
import dash_bootstrap_components as dbc
from data_loader import load_pipeline_health_summary
from utils.helpers import dataframe_value

logger = logging.getLogger(__name__)


def _bell(has_alerts):
    children = [html.I(className="bi bi-bell-fill fs-6 text-muted")]
    if has_alerts:
        children.append(
            html.Span(
                className="position-absolute top-0 start-100 translate-middle p-1 bg-danger border border-light rounded-circle"
            )
        )
    return children


def build_health_state(df_summary):
    """Render only health indicators; never fetch data or recreate export controls."""
    if df_summary is None or df_summary.empty:
        return (
            [dbc.DropdownMenuItem("Pipeline health unavailable", disabled=True)],
            _bell(False),
            "Pipeline Health",
            "warning",
            "",
            False,
            None,
        )

    status = dataframe_value(df_summary, "overall_system_status", "UNKNOWN")
    failed_count = int(dataframe_value(df_summary, "failed_tests", 0))
    warning_count = int(dataframe_value(df_summary, "warning_tests", 0))
    passed_count = int(dataframe_value(df_summary, "passed_tests", 0))
    last_check = str(dataframe_value(df_summary, "last_dbt_run", "N/A"))
    items = []
    if failed_count:
        items.append(
            dbc.DropdownMenuItem(
                f"🚨 {failed_count} dbt Test Failures Detected",
                href="/pipeline-health",
                className="text-danger",
            )
        )
    if warning_count or status == "WARNING":
        items.append(
            dbc.DropdownMenuItem(
                f"⚠️ Pipeline warning: {warning_count} test warnings",
                href="/pipeline-health",
                className="text-warning",
            )
        )
    has_alerts = failed_count > 0 or warning_count > 0 or status != "HEALTHY"
    if not has_alerts:
        items.append(
            dbc.DropdownMenuItem(
                f"✅ Pipeline healthy ({passed_count} tests passed)",
                className="text-success",
            )
        )
    elif not items:
        items.append(
            dbc.DropdownMenuItem(
                f"Pipeline status: {status}",
                href="/pipeline-health",
            )
        )
    items.append(dbc.DropdownMenuItem(f"Last pipeline run: {last_check[:19]}"))
    critical = failed_count > 0 or status == "CRITICAL"
    message = (
        f"Detected {failed_count} failing dbt assertions."
        if failed_count
        else f"Pipeline status: {status}; {warning_count} test warnings."
    )
    signature = (
        [status, failed_count, warning_count, last_check] if has_alerts else None
    )
    return (
        items,
        _bell(has_alerts),
        "Critical Pipeline Failure" if critical else "Pipeline Warning Alert",
        "danger" if critical else "warning",
        message,
        has_alerts,
        signature,
    )


@callback(
    Output("header-health-menu", "children"),
    Output("header-health-bell", "children"),
    Output("pipeline-alert-toast", "header"),
    Output("pipeline-alert-toast", "icon"),
    Output("header-health-toast-message", "children"),
    Output("pipeline-alert-toast", "is_open"),
    Output("header-health-alert-state", "data"),
    Input("url", "pathname"),
    Input("header-health-refresh", "n_intervals"),
    State("header-health-alert-state", "data"),
)
def refresh_header_health(_pathname, _n_intervals, previous_alert):
    try:
        df_summary = load_pipeline_health_summary()
    except Exception:
        logger.exception("Unable to refresh pipeline health")
        df_summary = None
    items, bell, title, icon, message, has_alerts, signature = build_health_state(
        df_summary
    )
    # Keep a dismissed toast closed until the alert or pipeline run changes.
    is_open = no_update if has_alerts and signature == previous_alert else has_alerts
    return items, bell, title, icon, message, is_open, signature


def create_header():
    """Build a query-free shell; the callback refreshes health after page load."""
    return html.Div(
        className="top-header-bar d-flex align-items-center justify-content-between px-4 py-3 mb-4 rounded-3 position-relative",
        children=[
            dcc.Interval(id="header-health-refresh", interval=60_000, n_intervals=0),
            dcc.Store(id="header-health-alert-state"),
            # Left: Welcome Greeting
            html.Div(
                [
                    html.Div(
                        [
                            html.H4(
                                "Welcome back, Roel! 👋",
                                className="text-white fw-bold mb-1 fs-5",
                            ),
                            html.P(
                                "Here's an overview of your store's latest performance and pipeline observability.",
                                className="text-muted small mb-0 fs-7",
                            ),
                        ]
                    )
                ],
                className="d-flex align-items-center",
            ),
            # Right: Notification Bell & Action Buttons
            html.Div(
                [
                    # Dynamic Notification Bell
                    dbc.DropdownMenu(
                        label=dcc.Loading(
                            id="header-health-loading",
                            type="circle",
                            color="#10b981",
                            fullscreen=False,
                            children=html.Div(
                                id="header-health-bell",
                                children=_bell(False),
                                className="position-relative d-inline-block",
                            ),
                        ),
                        children=html.Div(
                            "Checking pipeline health…",
                            id="header-health-menu",
                            className="dark-card shadow-lg border border-secondary p-1 rounded",
                        ),
                        nav=False,
                        in_navbar=False,
                        toggle_style={
                            "backgroundColor": "transparent",
                            "border": "1px solid #6c757d",
                            "padding": "0.5rem 0.75rem",
                        },
                        className="me-2 header-icon-btn rounded-3",
                        align_end=True,
                    ),
                    # Report Modal Trigger
                    dbc.Button(
                        [
                            html.I(className="bi bi-file-earmark-text me-2"),
                            html.Span("Preview & Export"),
                        ],
                        id="global-export-btn",
                        color="primary",
                        className="export-btn rounded-3 px-3 py-2 fw-semibold border-0",
                    ),
                    dcc.Download(id="global-download-file"),
                ],
                className="d-flex align-items-center",
            ),
            # Ingestion Alert Toast Container (Positioned top-right)
            dbc.Toast(
                [
                    html.P(
                        id="header-health-toast-message",
                        className="mb-1 text-white small",
                    ),
                    html.A(
                        "View Details in Pipeline Health →",
                        href="/pipeline-health",
                        className="text-info small fw-bold text-decoration-none",
                    ),
                ],
                id="pipeline-alert-toast",
                header="Pipeline Health",
                icon="warning",
                is_open=False,
                dismissable=True,
                duration=8000,  # Auto-dismisses after 8 seconds
                style={
                    "position": "fixed",
                    "top": "20px",
                    "right": "20px",
                    "zIndex": 9999,
                    "minWidth": "320px",
                },
                className="dark-card border border-secondary shadow-lg",
            ),
            # Executive Report Preview Modal
            dbc.Modal(
                [
                    dbc.ModalHeader(
                        dbc.ModalTitle(
                            "Executive Report Preview", className="fw-bold text-white"
                        ),
                        close_button=True,
                    ),
                    dbc.ModalBody(
                        html.Div(id="export-modal-body-content"),
                        style={"maxHeight": "70vh", "overflowY": "auto"},
                    ),
                    dbc.ModalFooter(
                        [
                            dbc.Button(
                                "Cancel",
                                id="close-export-modal-btn",
                                color="secondary",
                                outline=True,
                                className="me-2",
                            ),
                            dbc.Button(
                                [
                                    html.I(className="bi bi-download me-2"),
                                    html.Span("Download CSV Report"),
                                ],
                                id="confirm-download-btn",
                                color="success",
                                className="fw-semibold",
                            ),
                        ]
                    ),
                ],
                id="export-preview-modal",
                size="xl",
                is_open=False,
                centered=True,
            ),
        ],
    )

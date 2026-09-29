import logging

from dash import html, dcc, callback, Input, Output, State, no_update
import dash_bootstrap_components as dbc
from data_loader import load_pipeline_health_summary
from utils.helpers import dataframe_value
from components.panels import loading

logger = logging.getLogger(__name__)


def _bell(has_alerts):
    return [
        html.I(className="bi bi-bell", **{"aria-hidden": "true"}),
        html.Span("Pipeline alerts" if has_alerts else "Pipeline status"),
        html.Span(className="health-dot alert-dot" if has_alerts else "health-dot"),
    ]


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
                f"{failed_count} dbt Test Failures Detected",
                href="/pipeline-health",
                className="text-danger",
            )
        )
    if warning_count or status == "WARNING":
        items.append(
            dbc.DropdownMenuItem(
                f"Pipeline warning: {warning_count} test warnings",
                href="/pipeline-health",
                className="text-warning",
            )
        )
    has_alerts = failed_count > 0 or warning_count > 0 or status != "HEALTHY"
    if not has_alerts:
        items.append(
            dbc.DropdownMenuItem(
                f"Pipeline healthy ({passed_count} tests passed)",
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


PAGE_HEADINGS = {
    "/": ("Product Overview", "Revenue, demand, and product performance"),
    "/customers": ("Customer 360", "Customer value, engagement, and retention"),
    "/pipeline-health": (
        "Pipeline Health",
        "Latest loads, test coverage, and execution history",
    ),
}


@callback(
    Output("dashboard-page-title", "children"),
    Output("dashboard-page-subtitle", "children"),
    Output("global-export-btn", "disabled"),
    Input("url", "pathname"),
)
def update_page_heading(pathname):
    title, subtitle = PAGE_HEADINGS.get(pathname, ("Analytics", "Explore your data"))
    return title, subtitle, pathname not in ("/", "/customers")


def create_header():
    return html.Header(
        [
            dcc.Interval(id="header-health-refresh", interval=60_000, n_intervals=0),
            dcc.Store(id="header-health-alert-state"),
            html.Div(
                [
                    html.H1("Product Overview", id="dashboard-page-title"),
                    html.P(
                        "Revenue, demand, and product performance",
                        id="dashboard-page-subtitle",
                    ),
                ],
                className="page-heading",
            ),
            html.Div(
                [
                    dbc.DropdownMenu(
                        label=loading(
                            html.Div(id="header-health-bell", children=_bell(False)),
                            "header-health-loading",
                        ),
                        children=html.Div(
                            "Checking pipeline health…", id="header-health-menu"
                        ),
                        className="header-health-menu",
                        align_end=True,
                        caret=False,
                        toggle_class_name="health-toggle",
                    ),
                    dbc.Button(
                        [
                            html.I(
                                className="bi bi-download", **{"aria-hidden": "true"}
                            ),
                            "Preview & export",
                        ],
                        id="global-export-btn",
                        className="export-btn",
                        color="primary",
                    ),
                    dcc.Download(id="global-download-file"),
                ],
                className="header-actions",
            ),
            dbc.Toast(
                [
                    html.P(id="header-health-toast-message"),
                    html.A("View pipeline health", href="/pipeline-health"),
                ],
                id="pipeline-alert-toast",
                header="Pipeline Health",
                icon="warning",
                is_open=False,
                dismissable=True,
                duration=8000,
                className="pipeline-toast",
            ),
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle("Executive report preview")),
                    dbc.ModalBody(
                        loading(
                            html.Div(id="export-modal-body-content"),
                            "export-preview-loading",
                        ),
                        className="export-modal-body",
                    ),
                    dbc.ModalFooter(
                        [
                            dbc.Button(
                                "Cancel",
                                id="close-export-modal-btn",
                                color="secondary",
                                outline=True,
                            ),
                            dbc.Button(
                                "Download CSV report",
                                id="confirm-download-btn",
                                color="primary",
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
        className="top-header-bar",
    )

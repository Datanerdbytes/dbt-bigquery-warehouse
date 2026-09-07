import dash
from dash import html
import dash_bootstrap_components as dbc

def create_kpi_card(title, card_id):
    """Generates an individual KPI Column"""
    return dbc.Col(
        html.Div(
            [
                html.Div(
                    [
                        html.H6(title, className="text-muted fw-bold mb-1 small text-uppercase"),
                        html.Span("•••", className="text-muted small cursor-pointer")
                    ],
                    className="d-flex justify-content-between align-items-center mb-2"
                ),
                html.Div(
                    [
                        html.Span(id=f"{card_id}-value", className="kpi-number text-white"),
                        html.Span(id=f"{card_id}-badge", className="kpi-badge ms-2")
                    ],
                    className="kpi-value-container"
                ),
                dbc.Tooltip(id=f"{card_id}-tooltip", target=f"{card_id}-card", placement="bottom")
            ],
            id=f"{card_id}-card",
            className="dark-card p-3 rounded shadow-sm cursor-pointer h-100"
        ),
        width=12, sm=6, md=3
    )

def create_kpi_bar(kpi_list):
    """
    Wraps multiple KPI cards inside a single responsive Row wrapper.
    Usage: create_kpi_bar([("TOTAL SALES", "kpi-sales"), ("TOTAL ORDERS", "kpi-orders")])
    """
    return dbc.Row(
        [create_kpi_card(title, card_id) for title, card_id in kpi_list],
        className="g-2 mb-3"
    )
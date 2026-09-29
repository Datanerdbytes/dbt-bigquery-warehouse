from dash import html
import dash_bootstrap_components as dbc


def create_kpi_card(title, card_id):
    return html.Div(
        [
            html.H2(title, className="kpi-label"),
            html.Div("—", id=f"{card_id}-value", className="kpi-number"),
            html.Div(id=f"{card_id}-badge", className="kpi-badge"),
            dbc.Tooltip(
                id=f"{card_id}-tooltip", target=f"{card_id}-card", placement="bottom"
            ),
        ],
        id=f"{card_id}-card",
        className="kpi-card",
    )


def create_kpi_bar(kpi_list):
    return html.Div(
        [create_kpi_card(title, card_id) for title, card_id in kpi_list],
        className="kpi-grid",
    )

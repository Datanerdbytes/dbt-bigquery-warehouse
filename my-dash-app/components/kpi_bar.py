import dash_bootstrap_components as dbc
from dash import dcc, html


def create_kpi_card(title, card_id, *, sparklines=False):
    return html.Div(
        [
            html.H2(title, className="kpi-label"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                "—", id=f"{card_id}-value", className="kpi-number"
                            ),
                            dbc.Badge(
                                id=f"{card_id}-badge",
                                color="var(--dashboard-raised)",
                                pill=True,
                                className="kpi-badge",
                            ),
                        ],
                        className="kpi-summary",
                    ),
                    (
                        html.Div(
                            dcc.Graph(
                                id=f"{card_id}-sparkline",
                                config={
                                    "displayModeBar": False,
                                    "responsive": True,
                                    "scrollZoom": False,
                                },
                                animate=False,
                                className="kpi-sparkline",
                            ),
                            id=f"{card_id}-sparkline-container",
                            className="kpi-sparkline-container",
                            role="group",
                            **{
                                "aria-label": f"{title}: per-period trend for the selected dates, category and country. Each point describes one period, not cumulative activity."
                            },
                        )
                        if sparklines
                        else None
                    ),
                ],
                className="kpi-content" if sparklines else "",
            ),
            dbc.Tooltip(
                id=f"{card_id}-tooltip",
                target=f"{card_id}-card",
                placement="bottom",
            ),
        ],
        id=f"{card_id}-card",
        className="kpi-card kpi-card-with-trend" if sparklines else "kpi-card",
    )


def create_kpi_bar(kpi_list, *, sparklines=False):
    return html.Div(
        [
            create_kpi_card(title, card_id, sparklines=sparklines)
            for title, card_id in kpi_list
        ],
        className="kpi-grid",
    )

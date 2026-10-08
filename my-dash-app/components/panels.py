"""Shared, query-free panels and grid defaults for all dashboard pages."""

import dash_ag_grid as dag
from dash import dcc, html

# pyrefly: ignore [missing-import]
from theme import COLORS


def loading(component, loading_id):
    return dcc.Loading(
        id=loading_id,
        type="circle",
        color=COLORS["spinner"],
        fullscreen=False,
        children=component,
    )


def panel(
    title, child, class_name="", description=None, *, actions=None, title_id=None
):
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H2(
                                title,
                                className="panel-title",
                                **({"id": title_id} if title_id else {}),
                            ),
                            (
                                html.P(description, className="panel-description")
                                if description
                                else None
                            ),
                        ]
                    ),
                    actions,
                ],
                className=(
                    "panel-heading panel-heading-actions"
                    if actions is not None
                    else "panel-heading"
                ),
            ),
            html.Div(child, className="panel-content"),
        ],
        className=f"dashboard-panel {class_name}",
    )


def chart_panel(
    title,
    graph_id,
    loading_id,
    class_name="",
    description=None,
    *,
    actions=None,
    title_id=None,
    footer=None,
):
    return panel(
        title,
        [
            loading(
                dcc.Graph(
                    id=graph_id,
                    config={"displayModeBar": False, "responsive": True},
                    className="dashboard-chart",
                ),
                loading_id,
            ),
            footer,
        ],
        class_name,
        description,
        actions=actions,
        title_id=title_id,
    )


def create_grid(
    column_defs, rows=None, grid_id=None, class_name="", options=None, row_id=None
):
    kwargs = {"id": grid_id} if grid_id else {}
    if row_id is not None:
        kwargs["getRowId"] = row_id
    return dag.AgGrid(
        **kwargs,
        columnDefs=column_defs,
        rowData=[] if rows is None else rows,
        dashGridOptions={
            "theme": "themeBalham",
            "animateRows": True,
            "pagination": True,
            "paginationPageSize": 10,
            "paginationPageSizeSelector": False,
            "rowHeight": 36,
            "headerHeight": 36,
            **(options or {}),
        },
        columnSize="responsiveSizeToFit",
        defaultColDef={
            "filter": True,
            "sortable": True,
            "resizable": True,
            "minWidth": 100,
        },
        className=f"analytics-grid {class_name}",
    )

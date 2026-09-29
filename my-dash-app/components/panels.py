"""Shared, query-free panels and grid defaults for all dashboard pages."""

from dash import dcc, html
import dash_ag_grid as dag
from theme import COLORS


def loading(component, loading_id):
    return dcc.Loading(
        id=loading_id,
        type="circle",
        color=COLORS["spinner"],
        fullscreen=False,
        children=component,
    )


def panel(title, child, class_name="", description=None):
    return html.Section(
        [
            html.Div(
                [
                    html.H2(title, className="panel-title"),
                    (
                        html.P(description, className="panel-description")
                        if description
                        else None
                    ),
                ],
                className="panel-heading",
            ),
            html.Div(child, className="panel-content"),
        ],
        className=f"dashboard-panel {class_name}",
    )


def chart_panel(title, graph_id, loading_id, class_name="", description=None):
    return panel(
        title,
        loading(
            dcc.Graph(
                id=graph_id,
                config={"displayModeBar": False, "responsive": True},
                className="dashboard-chart",
            ),
            loading_id,
        ),
        class_name,
        description,
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

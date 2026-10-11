"""Revenue and gross margin using standard product costs, aggregated by period."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from theme import COLORS, style_figure


def aggregate_sales_trend(frame, frequency):
    data = frame.reindex(
        columns=["order_date", "gross_sales_amount", "quantity", "cost"]
    ).copy()
    for column in ("gross_sales_amount", "quantity", "cost"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    valid = (
        np.isfinite(data[["gross_sales_amount", "quantity", "cost"]]).all(axis=1)
        & data["cost"].ge(0)
        & data["quantity"].ge(0)
    )
    data["total_cost"] = (data["quantity"] * data["cost"]).where(valid)
    data["missing_cost"] = ~valid
    trend = (
        data.set_index("order_date")
        .resample(frequency)
        .agg(
            revenue=("gross_sales_amount", "sum"),
            total_cost=("total_cost", "sum"),
            missing_cost=("missing_cost", "sum"),
        )
        .reset_index()
    )
    eligible = trend["revenue"].gt(0) & trend["missing_cost"].eq(0)
    trend["margin"] = (trend["revenue"] - trend["total_cost"]) / trend["revenue"].where(
        eligible
    )
    return trend


def sales_trend_figure(frame, frequency):
    trend = aggregate_sales_trend(frame, frequency)
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Bar(
            x=trend["order_date"],
            y=trend["revenue"],
            name="Sales revenue",
            marker_color=COLORS["accent"],
            hovertemplate="Revenue: $%{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=trend["order_date"],
            y=trend["margin"],
            name="Gross profit margin",
            mode="lines+markers",
            connectgaps=False,
            line=dict(color=COLORS["success"], width=3),
            marker=dict(size=6),
            hovertemplate="Gross profit margin: %{y:.1%}<extra></extra>",
        ),
        secondary_y=True,
    )
    style_figure(figure)
    figure.update_layout(
        hovermode="x unified",
        bargap=0.25,
        legend=dict(orientation="h", y=1.15, x=0),
        margin=dict(l=12, r=12, t=42, b=24),
    )
    figure.update_xaxes(title_text="", showgrid=False)
    figure.update_yaxes(
        title_text="Revenue ($)", tickprefix="$", rangemode="tozero", secondary_y=False
    )
    margins = trend["margin"].dropna()
    lower = min(0, float(margins.min())) if not margins.empty else 0
    figure.update_yaxes(
        title_text="Margin (%)",
        tickformat=".0%",
        tickmode="linear",
        tick0=0,
        dtick=max(0.25, round(abs(lower) / 4, 2)),
        showgrid=False,
        range=[lower - (0.05 if lower < 0 else 0), 1],
        secondary_y=True,
    )
    if trend["missing_cost"].any():
        figure.add_annotation(
            text="Margin unavailable for periods with missing or invalid costs.",
            x=0,
            y=1.28,
            xref="paper",
            yref="paper",
            xanchor="left",
            showarrow=False,
            font=dict(size=11, color=COLORS["muted"]),
        )
        figure.update_layout(margin_t=65)
    return figure

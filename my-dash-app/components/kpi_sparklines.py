"""Filter-scoped, per-period KPI trends; input frames remain read-only."""

import pandas as pd
import plotly.graph_objects as go
from plotly.colors import hex_to_rgb
from theme import COLORS, style_figure

METRICS = {
    "product": [
        ("Revenue", "$,.2f"),
        ("Orders", ",.0f"),
        ("Units sold", ",.0f"),
        ("Customers", ",.0f"),
    ],
    "customer": [
        ("Active customers", ",.0f"),
        ("Average spend", "$,.2f"),
        ("Order frequency", ".2f"),
        ("Repeat rate", ".1f"),
    ],
}


def aggregate_kpi_trends(frame, start, end, page):
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    weekly = (end - start).days + 1 <= 60
    starts = (
        pd.date_range(start, end, freq="7D")
        if weekly
        else pd.date_range(start.to_period("M").start_time, end, freq="MS")
    )
    rows = []
    for boundary in starts:
        natural_end = (
            boundary + pd.Timedelta(days=6)
            if weekly
            else boundary + pd.offsets.MonthEnd(0)
        )
        left, right = max(boundary, start), min(natural_end, end)
        subset = frame.loc[
            (frame["order_date"] >= left)
            & (frame["order_date"] < right + pd.Timedelta(days=1))
        ]
        if page == "product":
            values = [
                subset["gross_sales_amount"].sum(),
                subset["order_number"].nunique(),
                subset["quantity"].sum(),
                subset["customer_key"].nunique(),
            ]
        else:
            customers = subset.groupby("customer_key").agg(
                revenue=("gross_sales_amount", "sum"),
                orders=("order_number", "nunique"),
            )
            count = len(customers)
            values = [
                count,
                customers.revenue.sum() / count if count else None,
                customers.orders.sum() / count if count else None,
                customers.orders.gt(1).sum() / count * 100 if count else None,
            ]
        label = f"{left:%b %d, %Y} – {right:%b %d, %Y}"
        if left == right:
            hover_period = f"{left:%b} {left.day}, {left.year}"
        elif left.year != right.year:
            hover_period = f"{left:%b} {left.day}, {left.year}–{right:%b} {right.day}, {right.year}"
        elif left.month != right.month:
            hover_period = f"{left:%b} {left.day}–{right:%b} {right.day}, {right.year}"
        else:
            hover_period = f"{left:%b} {left.day}–{right.day}, {right.year}"
        if left != boundary or right != natural_end:
            label += " (partial period)"
            hover_period += "<br>Partial period"
        rows.append([left, label, hover_period, *values])
    return pd.DataFrame(
        rows,
        columns=[
            "date",
            "period",
            "hover_period",
            "metric0",
            "metric1",
            "metric2",
            "metric3",
        ],
    )


def kpi_sparkline_figures(frame=None, start=None, end=None, page="product"):
    trend = (
        aggregate_kpi_trends(frame, start, end, page)
        if frame is not None and not frame.empty and start and end
        else None
    )
    if trend is not None and trend.empty:
        trend = None
    figures = []
    for index, (_label, number_format) in enumerate(METRICS[page]):
        figure = style_figure(go.Figure(), height=64)
        figure.update_layout(
            margin=dict(l=3, r=3, t=6, b=6),
            showlegend=False,
            hovermode="closest",
            dragmode=False,
            transition_duration=0,
            hoverlabel=dict(font_size=11, align="left"),
        )
        figure.update_xaxes(visible=False, fixedrange=True)
        figure.update_yaxes(visible=False, fixedrange=True)
        if trend is None:
            figure.add_annotation(
                text="No trend data",
                x=0.5,
                y=0.5,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(size=10, color=COLORS["muted"]),
            )
        else:
            suffix = "%" if page == "customer" and index == 3 else ""
            valid = trend[f"metric{index}"].notna()
            shading = f"rgba{(*hex_to_rgb(COLORS['accent']), 0.12)}"
            figure.add_trace(
                go.Scatter(
                    x=trend.date,
                    y=trend[f"metric{index}"],
                    customdata=trend.period,
                    text=trend.hover_period,
                    mode=(
                        "lines+markers"
                        if valid.sum() == 1 or not valid.all()
                        else "lines"
                    ),
                    line=dict(color=COLORS["accent"], width=2),
                    marker=dict(size=5),
                    fill="tozeroy" if valid.all() else "none",
                    fillcolor=shading,
                    connectgaps=False,
                    hovertemplate=f"%{{text}}<br><b>%{{y:{number_format}}}{suffix}</b><extra></extra>",
                )
            )
            # Plotly's area fill can bridge missing values even with connectgaps
            # disabled. Shade only contiguous available periods in ratio trends.
            if not valid.all():
                for _, segment in trend.loc[valid].groupby((~valid).cumsum()):
                    figure.add_trace(
                        go.Scatter(
                            x=segment.date,
                            y=segment[f"metric{index}"],
                            mode="lines",
                            line=dict(width=0),
                            fill="tozeroy",
                            fillcolor=shading,
                            hoverinfo="skip",
                        )
                    )
        figures.append(figure)
    return tuple(figures)


def sparkline_descriptions(figures, page):
    """Expose trend endpoints without requiring a pointer or chart colors."""
    descriptions = []
    for index, (figure, (label, _)) in enumerate(
        zip(figures, METRICS[page], strict=True)
    ):
        if not figure.data:
            descriptions.append(f"{label}: No trend data for the selected filters.")
            continue
        trace = figure.data[0]
        points = [
            (period, value)
            for period, value in zip(trace.customdata, trace.y, strict=True)
            if pd.notna(value)
        ]
        if not points:
            descriptions.append(f"{label}: No trend data for the selected filters.")
            continue

        def formatted(value, index=index):
            if (page == "product" and index == 0) or (
                page == "customer" and index == 1
            ):
                return f"${value:,.2f}"
            if page == "customer" and index == 3:
                return f"{value:.1f}%"
            return (
                f"{value:.2f}" if page == "customer" and index == 2 else f"{value:,.0f}"
            )

        first, last = points[0], points[-1]
        descriptions.append(
            f"{label}: Per-period trend, not cumulative. First available period {first[0]}: {formatted(first[1])}. "
            f"Latest available period {last[0]}: {formatted(last[1])}. {len(trace.y)} periods in the selected range."
        )
    return tuple(descriptions)

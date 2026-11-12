"""Shared dashboard tokens. Run this module to regenerate assets/00-theme.css."""

# Dashdark X palette (Themewagon coded source, src/theme/colors.ts), softened
# on 2026-11-13: gentler indigo/violet/cyan accents and a calmer status ramp,
# keeping the original deep-navy chrome.
COLORS = {
    "background": "#081028",
    "surface": "#0B1739",
    "raised": "#0A1D50",
    "text": "#FFFFFF",
    "muted": "#AEB9E1",
    "border": "#343B4F",
    "accent": "#7C6AF8",
    "accent_secondary": "#5EC8F8",
    "accent_tertiary": "#0E43FB",
    "grid": "#1E2C4F",
    "success": "#45D48A",
    "warning": "#F5B95F",
    "danger": "#F27D77",
    "success_bg": "#45D48A33",
    "warning_bg": "#F5B95F33",
    "danger_bg": "#F27D7733",
    "purple": "#B46BFF",
    "spinner": "#5EC8F8",
}
FONTS = {
    "body": '"Work Sans", system-ui, sans-serif',
    "number": '"Mona Sans Variable", "Mona Sans", "Work Sans", system-ui, sans-serif',
    "display": '"Mona Sans Variable", "Mona Sans", "Work Sans", system-ui, sans-serif',
}
# Softened Dashdark chart sequence: indigo, violet, cyan, mint, amber, coral.
CHART_COLORWAY_KEYS = (
    "accent",
    "purple",
    "accent_secondary",
    "success",
    "warning",
    "danger",
)
SPACING = {"gap": "12px", "panel": "16px", "sidebar": "208px", "rail": "64px"}


def css_tokens():
    values = {**COLORS, **{f"font-{k}": v for k, v in FONTS.items()}, **SPACING}
    return (
        "/* Generated from theme.py; edit shared tokens there. */\n:root {\n"
        + "".join(f"  --dashboard-{k}: {v};\n" for k, v in values.items())
        + "  color-scheme: dark;\n}\n"
    )


def initialize_chart_templates():
    """Resolve lazy Plotly template children before concurrent callbacks run."""
    import plotly.express as px
    import plotly.io as pio

    # Express reads shared template trace defaults lazily. Concurrent first
    # access can replace child objects another callback is already reading.
    # Exercise the dashboard's chart families on the startup thread without
    # querying data or changing the configured templates/default palette.
    for template in dict.fromkeys((pio.templates.default or "plotly", "plotly_dark")):
        for chart in (px.area, px.bar, px.scatter, px.line):
            chart(x=[0, 1], y=[0, 1], template=template)
        px.pie(names=["startup"], values=[1], template=template)
        px.choropleth(locations=["USA"], color=[1], template=template)


def style_figure(fig, height=280):
    """Apply the same readable chart surfaces and typography on every page."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        font={"family": FONTS["body"], "color": COLORS["text"], "size": 12},
        colorway=[COLORS[k] for k in CHART_COLORWAY_KEYS],
        margin={"l": 12, "r": 22, "t": 24, "b": 16},
        height=height,
        hoverlabel={
            "bgcolor": COLORS["raised"],
            "font_color": COLORS["text"],
            "bordercolor": COLORS["border"],
        },
        legend={"font": {"color": COLORS["muted"]}},
    )
    fig.update_xaxes(color=COLORS["muted"], gridcolor=COLORS["border"], automargin=True)
    fig.update_yaxes(color=COLORS["muted"], gridcolor=COLORS["border"], automargin=True)
    return fig


if __name__ == "__main__":
    from pathlib import Path

    (Path(__file__).parent / "assets" / "00-theme.css").write_text(css_tokens())

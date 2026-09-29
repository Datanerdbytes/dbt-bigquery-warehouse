"""Shared dashboard tokens. Run this module to regenerate assets/00-theme.css."""

COLORS = {
    "background": "#0f172a",
    "surface": "#1b2336",
    "raised": "#263249",
    "text": "#f8fafc",
    "muted": "#a7b5c9",
    "border": "#354258",
    "accent": "#69a5ff",
    "success": "#5ddd98",
    "warning": "#f6c56b",
    "danger": "#ff8585",
    "purple": "#b6a0ff",
    "spinner": "#10b981",
}
FONTS = {
    "body": '"Fira Sans", system-ui, sans-serif',
    "number": '"Fira Code", ui-monospace, monospace',
}
SPACING = {"gap": "12px", "panel": "16px", "sidebar": "208px", "rail": "64px"}


def css_tokens():
    values = {**COLORS, **{f"font-{k}": v for k, v in FONTS.items()}, **SPACING}
    return (
        "/* Generated from theme.py; edit shared tokens there. */\n:root {\n"
        + "".join(f"  --dashboard-{k}: {v};\n" for k, v in values.items())
        + "  color-scheme: dark;\n}\n"
    )


def style_figure(fig, height=280):
    """Apply the same readable chart surfaces and typography on every page."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        font={"family": FONTS["body"], "color": COLORS["text"], "size": 12},
        colorway=[
            COLORS[k] for k in ("accent", "success", "purple", "warning", "danger")
        ],
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

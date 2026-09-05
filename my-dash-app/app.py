import dash
from dash import Dash, html
import dash_bootstrap_components as dbc

# Initialize the Multi-Page Dash App
app = Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.FLATLY],
    suppress_callback_exceptions=True
)

# Shared Navigation Bar
navbar = dbc.NavbarSimple(
    children=[
        dbc.NavItem(dbc.NavLink("Product Overview", href="/", active="exact")),
        dbc.NavItem(dbc.NavLink("Customer 360", href="/customers", active="exact")),
    ],
    brand="Enterprise Insights",
    brand_href="/",
    color="primary",
    dark=True,
    className="mb-3 shadow-sm",
)

# Root App Layout
app.layout = html.Div([
    navbar,
    html.Div(dash.page_container) # Edge-to-edge wrapper
])

if __name__ == "__main__":
    app.run(debug=True)
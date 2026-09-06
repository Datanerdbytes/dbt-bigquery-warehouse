import dash
from dash import Dash, html
import dash_bootstrap_components as dbc
from components.sidebar import create_sidebar
from components.header import create_header  # <-- Import Header

# Initialize the Multi-Page Dash App
app = Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[
        dbc.themes.DARKLY,
        dbc.icons.BOOTSTRAP  # Required for Bootstrap navigation & header icons
    ],
    suppress_callback_exceptions=True
)

# Root App Layout
app.layout = html.Div(
    [
        create_sidebar(),
        html.Div(
            [
                create_header(),  
                dash.page_container
            ],
            className="main-content-wrapper p-4"
        )
    ],
    className="d-flex app-wrapper"
)

if __name__ == "__main__":
    app.run(debug=True)
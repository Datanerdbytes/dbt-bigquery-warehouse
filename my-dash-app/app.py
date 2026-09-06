import dash
from dash import Dash, html
import dash_bootstrap_components as dbc
from components.sidebar import create_sidebar

app = Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[
        dbc.themes.DARKLY,
        dbc.icons.BOOTSTRAP  # Required for Bootstrap navigation icons
    ],
    suppress_callback_exceptions=True
)

app.layout = html.Div(
    [
        create_sidebar(),
        html.Div(
            dash.page_container,
            className="main-content-wrapper"
        )
    ],
    className="d-flex app-wrapper"
)

if __name__ == "__main__":
    app.run(debug=True)
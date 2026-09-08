import dash
from dash import Dash, html, dcc
import dash_bootstrap_components as dbc
from flask_caching import Cache
from utils.cache import cache
from components.sidebar import create_sidebar
from components.header import create_header  

# Initialize the Multi-Page Dash App
app = Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[
        dbc.themes.DARKLY,
        dbc.icons.BOOTSTRAP 
    ],
    suppress_callback_exceptions=True
)

# Attach cache instance to the Flask server
cache.init_app(app.server)

server = app.server

# Root App Layout
app.layout = html.Div(
    [
        # Session store for active UI filter selections across pages
        dcc.Store(id="global-filter-store", storage_type="session"),
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
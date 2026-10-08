"""Local real-app CSP fixture. No dotenv, production credentials, or cloud I/O.

Started only by csp-browser.test.mjs; binds an ephemeral loopback port. Supabase
user verification and dashboard data are synthetic; real auth guards, templates,
Dash renderer, callbacks, assets, and response headers remain installed.
"""

import base64
import importlib
import io
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from google.cloud import bigquery
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "my-dash-app"))
os.environ.update(
    NEXT_PUBLIC_SUPABASE_URL="https://csp-test.supabase.co",
    NEXT_PUBLIC_SUPABASE_ANON_KEY="mock-test-anon-key",
    AUTH_ALLOWED_EMAILS="test@example.com",
    AUTH_APP_ORIGIN="http://127.0.0.1",
    GCP_PROJECT_ID="mock-test-project",
    GCP_KEY_PATH="",
    GOOGLE_APPLICATION_CREDENTIALS="",
)

# Keep all patches active until this child process exits.
patch("dotenv.load_dotenv").start()
patch.object(
    bigquery,
    "Client",
    side_effect=AssertionError("Cloud access forbidden in CSP fixture"),
).start()
import auth
import data_loader

from utils.cache import cache

USER = {
    "id": "csp-test-user",
    "email": "test@example.com",
    "email_confirmed_at": "2026-01-01",
}


def encode(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")


TOKEN = f"{encode({'alg': 'HS256'})}.{encode({'exp': int(time.time()) + 3600})}.test-signature"


def fake_user(request, **kwargs):
    if request.full_url != "https://csp-test.supabase.co/auth/v1/user":
        raise AssertionError("Unexpected external verification URL")
    if request.get_header("Authorization") != f"Bearer {TOKEN}":
        raise auth.HTTPError(request.full_url, 401, "Synthetic invalid token", {}, None)
    return io.BytesIO(json.dumps(USER).encode())


patch.object(auth, "urlopen", side_effect=fake_user).start()
# Rate-limit behavior remains covered by auth tests. This single fixture server
# exercises many independent browser contexts in seconds, so isolate that limit.
original_limiter = auth.Limiter
fixture_limiters = []


def fixture_limiter(*args, **kwargs):
    limiter = original_limiter(*args, **kwargs, enabled=False)
    fixture_limiters.append(limiter)
    return limiter


patch.object(auth, "Limiter", side_effect=fixture_limiter).start()
DATA = pd.DataFrame(
    [
        dict(
            product_key="p1",
            customer_key="c1",
            order_date=pd.Timestamp("2026-01-15"),
            order_number="synthetic-1",
            quantity=2,
            gross_sales_amount=40,
            unit_price=20,
            product_name="Fixture Bike",
            category="bikes",
            country="PH",
            first_name="Test",
            last_name="User",
        ),
        dict(
            product_key="p2",
            customer_key="c2",
            order_date=pd.Timestamp("2026-02-15"),
            order_number="synthetic-2",
            quantity=1,
            gross_sales_amount=10,
            unit_price=10,
            product_name="Fixture Part",
            category="parts",
            country="US",
            first_name="Local",
            last_name="User",
        ),
    ]
)
patch.object(data_loader, "get_prepared_dataset", return_value=DATA).start()
for name in dir(data_loader):
    if name.startswith("load_") and name != "load_env":
        patch.object(data_loader, name, return_value=pd.DataFrame()).start()
with patch.object(cache, "init_app"):
    dashboard = importlib.import_module("app")
cache.init_app(dashboard.server, config={"CACHE_TYPE": "SimpleCache"})
httpd = make_server("127.0.0.1", 0, dashboard.server, threaded=True)
origin = f"http://127.0.0.1:{httpd.server_port}"
os.environ["AUTH_APP_ORIGIN"] = origin
print(json.dumps({"origin": origin, "token": TOKEN, "user": USER}), flush=True)
httpd.serve_forever()

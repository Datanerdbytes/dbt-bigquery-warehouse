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
    AUTH_APP_ORIGIN="http://127.0.0.1",
    GCP_PROJECT_ID="mock-test-project",
    GCP_KEY_PATH="",
    GOOGLE_APPLICATION_CREDENTIALS="",
    AUTH_PASSWORD_LOCKOUT_ENABLED="true",
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


ADMIN_TOKEN = TOKEN.rsplit(".", 1)[0] + ".admin-signature"
ADMIN_USER = dict(
    USER,
    id="11111111-1111-4111-8111-111111111111",
    email="admin@example.com",
    app_metadata={"qe_role": "admin", "qe_owner": True},
)
DIRECTORY_MEMBER = dict(
    USER,
    id="22222222-2222-4222-8222-222222222222",
    email="member@example.com",
    app_metadata={},
    created_at="2026-10-01T08:00:00Z",
)
DELETE_MEMBER = dict(
    USER,
    id="44444444-4444-4444-8444-444444444444",
    email="delete-test@example.com",
    app_metadata={"qe_suspended": True},
)
MANAGER_TOKEN = TOKEN.rsplit(".", 1)[0] + ".manager-signature"
MANAGER_USER = dict(
    USER,
    id="55555555-5555-4555-8555-555555555555",
    email="manager@example.com",
    app_metadata={"qe_role": "admin"},
)
DIRECTORY = {
    user["id"]: user
    for user in [
        ADMIN_USER,
        DIRECTORY_MEMBER,
        DELETE_MEMBER,
        dict(
            USER,
            id="33333333-3333-4333-8333-333333333333",
            email="pending@example.com",
            email_confirmed_at=None,
        ),
    ]
}


def fake_user(request, **kwargs):
    if request.full_url != "https://csp-test.supabase.co/auth/v1/user":
        raise AssertionError("Unexpected external verification URL")
    value = request.get_header("Authorization")
    if value == f"Bearer {TOKEN}":
        user = USER
    elif value == f"Bearer {ADMIN_TOKEN}":
        user = ADMIN_USER
    elif value == f"Bearer {MANAGER_TOKEN}":
        user = MANAGER_USER
    else:
        raise auth.HTTPError(request.full_url, 401, "Synthetic invalid token", {}, None)
    return io.BytesIO(json.dumps(user).encode())


import user_admin


def fake_admin_request(method, path, body=None):
    if method == "GET" and path.startswith("?page="):
        from urllib.parse import parse_qs

        page = int(parse_qs(path[1:])["page"][0])
        return {"users": list(DIRECTORY.values())[(page - 1) * 25 : page * 25]}
    target = DIRECTORY.get(path.lstrip("/"))
    if target is None:
        raise user_admin.AdminError("user_not_found", 404)
    if method == "DELETE":
        assert body == {"should_soft_delete": False}
        del DIRECTORY[target["id"]]
        return {}
    if method == "PUT":
        target.setdefault("app_metadata", {}).update(body.get("app_metadata", {}))
    return target


patch.object(user_admin, "_service_request", side_effect=fake_admin_request).start()


# Password gateway exercises the real Flask route; only provider/storage I/O is fake.
from threading import Lock
from uuid import uuid4

import password_auth

password_states = {}
password_state_lock = Lock()


def fake_password_request(path, body, privileged=False):
    if path == "/rest/v1/rpc/qe_account_deletion_guard_ready":
        assert privileged
        return {"ready": True}
    if path == "/auth/v1/token?grant_type=password":
        if body["password"] == "incorrect-password":
            raise password_auth.PasswordAuthError("invalid_credentials", 401)
        return {"access_token": TOKEN, "refresh_token": "synthetic-refresh"}
    assert privileged and path == "/rest/v1/rpc/qe_password_attempt"
    with password_state_lock:
        state = password_states.setdefault(body["p_email"], {"failures": 0})
        if state["failures"] >= 5:
            return {"allowed": False, "error": "account_locked", "retry_after": 900}
        if body["p_action"] == "start":
            state["lease"] = str(uuid4())
            return {"allowed": True, "attempt_id": state["lease"], "retry_after": 0}
        if body["p_action"] == "status":
            return {"allowed": True, "retry_after": 0}
        assert body["p_attempt"] == state["lease"]
        if body["p_valid"] is False:
            state["failures"] += 1
            return {
                "allowed": False,
                "error": (
                    "account_locked"
                    if state["failures"] >= 5
                    else "invalid_credentials"
                ),
                "retry_after": 900 if state["failures"] >= 5 else 0,
            }
        if body["p_valid"] is True:
            state["failures"] = 0
        return {
            "allowed": body["p_valid"] is True,
            "error": "auth_unavailable",
            "retry_after": 0,
        }


patch.object(password_auth, "_request", side_effect=fake_password_request).start()

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
            cost=12,
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
            cost=7,
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
print(
    json.dumps(
        {
            "origin": origin,
            "token": TOKEN,
            "user": USER,
            "adminToken": ADMIN_TOKEN,
            "adminUser": ADMIN_USER,
            "managerToken": MANAGER_TOKEN,
            "managerUser": MANAGER_USER,
        }
    ),
    flush=True,
)
httpd.serve_forever()

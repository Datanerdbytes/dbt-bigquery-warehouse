"""Keep the free Supabase project awake and verify it in the same request.

Supabase pauses a Free project after seven days without database traffic, so a
scheduled job has to reach the database every day. The Vercel cron invokes this
route once a day with the deployment's CRON_SECRET, and the route runs one
read-only PostgREST query against the lockout table. That query counts as
database activity and also proves that the service-role key works and that the
SQL migrations were applied.

Vercel cron requests never follow a redirect, so this route answers with a
status code instead of handing the request to the login page.
"""

import json
import os
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from flask import jsonify, request

LOCKOUT_TABLE = "qe_password_attempts"


class KeepAwakeError(Exception):
    def __init__(self, code, status=503):
        self.code, self.status = code, status
        super().__init__(code)


def _query_database():
    """Run one read-only PostgREST query and return the number of rows."""
    from auth import AuthError, settings

    try:
        url, _, _ = settings()
    except AuthError:
        raise KeepAwakeError("auth_not_configured") from None
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    parsed = urlsplit(url)
    if (
        not key
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise KeepAwakeError("service_role_not_configured")
    query = urlencode({"select": "email", "limit": "1"})
    req = Request(
        f"{url}/rest/v1/{LOCKOUT_TABLE}?{query}",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=8) as response:
            raw = response.read(65537)
    except HTTPError as error:
        if error.code in (401, 403):
            raise KeepAwakeError("service_role_rejected") from None
        if error.code == 404:
            raise KeepAwakeError("migrations_missing") from None
        raise KeepAwakeError("supabase_unreachable") from None
    except (URLError, TimeoutError, OSError):
        raise KeepAwakeError("supabase_unreachable") from None
    if len(raw) > 65536:
        raise KeepAwakeError("supabase_unreachable")
    try:
        rows = json.loads(raw)
    except ValueError:
        raise KeepAwakeError("supabase_unreachable") from None
    if not isinstance(rows, list):
        raise KeepAwakeError("supabase_unreachable")
    return len(rows)


def install_keepawake(server):
    @server.get("/keepawake")
    def keepawake():
        secret = os.getenv("CRON_SECRET", "")
        if not secret:
            # Fail closed: without the secret nobody may reach the project.
            return jsonify(error="keepawake_not_configured"), 503
        header = request.headers.get("Authorization", "")
        if not secrets.compare_digest(header.encode(), f"Bearer {secret}".encode()):
            return jsonify(error="unauthorized"), 401
        try:
            rows = _query_database()
        except KeepAwakeError as error:
            return jsonify(error=error.code), error.status
        return jsonify(status="ok", rows=rows)

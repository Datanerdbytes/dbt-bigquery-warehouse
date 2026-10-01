"""Supabase identity verification and the Flask/Dash authorization boundary."""

import base64
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import g, jsonify, redirect, render_template, request

COOKIE = "qe_access_token"
PUBLIC = {
    "/login",
    "/signup",
    "/auth/callback",
    "/auth/session",
    "/auth/config",
    "/healthz",
}
PUBLIC_ASSETS = {
    "/assets/00-theme.css",
    "/assets/08-auth.css",
    "/assets/auth.bundle.js",
    "/assets/showcase.bundle.js",
}


class AuthError(Exception):
    def __init__(self, code, status):
        self.code, self.status = code, status
        super().__init__(code)


def settings():
    url = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    key = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    origin = os.getenv("AUTH_APP_ORIGIN", "").rstrip("/")
    parsed = urlsplit(origin)
    local = parsed.hostname in {"localhost", "127.0.0.1"}
    if (
        not url.startswith("https://")
        or not key
        or not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username
        or (parsed.scheme != "https" and not (local and parsed.scheme == "http"))
    ):
        raise AuthError("auth_not_configured", 503)
    return url, key, origin, parsed.scheme == "https"


def verify_access(token):
    url, key, _, _ = settings()
    if not isinstance(token, str) or not token or len(token) > 3500:
        raise AuthError("session_required", 401)
    try:
        req = Request(
            f"{url}/auth/v1/user",
            headers={"apikey": key, "Authorization": f"Bearer {token}"},
        )
        with urlopen(req, timeout=8) as response:
            user = json.load(response)
    except HTTPError as error:
        raise AuthError(
            "session_expired" if error.code in (401, 403) else "auth_unavailable",
            401 if error.code in (401, 403) else 503,
        ) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise AuthError("auth_unavailable", 503) from None
    if not isinstance(user, dict) or not user.get("id"):
        raise AuthError("session_expired", 401)
    if not user.get("email_confirmed_at"):
        raise AuthError("email_confirmation_required", 403)
    allowed = {
        x.strip().casefold()
        for x in os.getenv("AUTH_ALLOWED_EMAILS", "").split(",")
        if x.strip()
    }
    if str(user.get("email", "")).casefold() not in allowed:
        raise AuthError("approval_required", 403)
    # Decode expiry only after remote verification; identity always comes from Auth.
    try:
        payload = token.split(".")[1]
        claims = json.loads(
            base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        )
        remaining = int(claims["exp"]) - int(time.time())
    except (ValueError, KeyError, IndexError, TypeError):
        raise AuthError("session_expired", 401) from None
    if remaining <= 0:
        raise AuthError("session_expired", 401)
    return user, remaining


def install_auth(server):
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    server.template_folder = str(Path(__file__).parent / "templates")

    @server.before_request
    def protect():
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            try:
                _, _, origin, _ = settings()
            except AuthError as error:
                return jsonify(error=error.code), error.status
            if request.headers.get("Origin") != origin:
                return jsonify(error="origin_rejected"), 403
        # The public product page never needs dashboard data or a valid session.
        # Preserve the existing root redirect for verified, approved members.
        if request.path == "/" and request.method in {"GET", "HEAD"}:
            if request.cookies.get(COOKIE):
                try:
                    g.auth_user, _ = verify_access(request.cookies.get(COOKIE))
                except AuthError:
                    pass
                else:
                    return redirect("/dashboard")
            return render_template("landing.html")
        if request.path in PUBLIC or request.path in PUBLIC_ASSETS:
            return None
        try:
            g.auth_user, _ = verify_access(request.cookies.get(COOKIE))
        except AuthError as error:
            if request.method in {"GET", "HEAD"} and not request.path.startswith(
                ("/_dash", "/assets/")
            ):
                if error.status in (401, 403):
                    return redirect("/login")
                return render_template("auth.html", mode="unavailable"), 503
            return jsonify(error=error.code), error.status

    @server.after_request
    def private(response):
        response.headers["Cache-Control"] = "private, no-store"
        response.vary.add("Cookie")
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @server.get("/auth/config")
    def config():
        try:
            url, key, _, _ = settings()
        except AuthError as error:
            return jsonify(error=error.code), error.status
        return jsonify(url=url, anonKey=key)

    @server.get("/healthz")
    def health():
        return jsonify(status="ok")

    @server.get("/login")
    @server.get("/signup")
    @server.get("/auth/callback")
    def auth_page():
        return render_template(
            "auth.html",
            mode={"/login": "login", "/signup": "signup"}.get(request.path, "callback"),
        )

    @server.route("/auth/session", methods=["POST", "DELETE", "GET"])
    def session_bridge():
        if request.method == "GET":
            return jsonify(error="method_not_allowed"), 405
        _, _, _, secure = settings()
        if request.method == "DELETE":
            response = jsonify(ok=True)
            response.delete_cookie(
                COOKIE, path="/", secure=secure, httponly=True, samesite="Lax"
            )
            return response
        body = request.get_json(silent=True)
        token = body.get("access_token") if isinstance(body, dict) else None
        try:
            _, remaining = verify_access(token)
        except AuthError as error:
            response = jsonify(error=error.code)
            response.status_code = error.status
            response.delete_cookie(
                COOKIE, path="/", secure=secure, httponly=True, samesite="Lax"
            )
            return response
        response = jsonify(ok=True)
        response.set_cookie(
            COOKIE,
            token,
            max_age=remaining,
            secure=secure,
            httponly=True,
            samesite="Lax",
            path="/",
        )
        return response

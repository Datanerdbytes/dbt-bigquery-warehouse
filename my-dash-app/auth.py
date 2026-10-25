"""Supabase identity verification and the Flask/Dash authorization boundary."""

import base64
import json
import os
import secrets
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import g, jsonify, redirect, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from password_auth import (
    PasswordAuthError,
    ensure_not_locked,
    password_sign_in,
)
from password_auth import (
    enabled as lockout_enabled,
)
from user_admin import account_suspended, install_admin_routes, is_admin

COOKIE = "qe_access_token"
PUBLIC = {
    "/login",
    "/signup",
    "/forgot-password",
    "/reset-password",
    "/auth/callback",
    "/auth/session",
    "/auth/password",
    "/auth/config",
    "/healthz",
}
PUBLIC_ASSETS = {
    "/assets/00-theme.css",
    "/assets/08-auth.css",
    "/assets/auth.bundle.js",
    "/assets/showcase.bundle.js",
    "/assets/animations/workspace-overview.webm",
    "/assets/animations/workspace-overview.mp4",
    "/assets/animations/workspace-overview-poster.png",
    "/assets/animations/data-lineage.webm",
    "/assets/animations/data-lineage.mp4",
    "/assets/animations/data-lineage-poster.png",
}


def _generate_nonce() -> str:
    """Generate a cryptographically random CSP nonce."""
    return secrets.token_urlsafe(16)


class AuthError(Exception):
    def __init__(self, code, status):
        self.code, self.status = code, status
        super().__init__(code)


# Generic error messages to prevent account enumeration
GENERIC_AUTH_ERROR = "Invalid email or password"
GENERIC_SESSION_ERROR = "Authentication failed"


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
    email = user.get("email")
    if (
        not isinstance(email, str)
        or not email.strip()
        or not user.get("email_confirmed_at")
    ):
        raise AuthError("email_confirmation_required", 403)
    if account_suspended(user):
        raise AuthError("account_suspended", 403)
    try:
        ensure_not_locked(email)
    except PasswordAuthError as error:
        raise AuthError(
            error.code, 403 if error.code == "account_locked" else 503
        ) from None
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


def _rate_limit_exceeded_handler(e):
    """Return a non-enumerating error that distinguishes throttling from login."""
    if request.endpoint == "auth_page":
        return render_template("auth.html", mode="rate_limited"), 429
    return jsonify(error="rate_limited"), 429


def install_auth(server):
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    server.template_folder = str(Path(__file__).parent / "templates")

    install_admin_routes(server)

    # Initialize rate limiter
    limiter = Limiter(
        get_remote_address,
        app=server,
        storage_uri="memory://",
    )

    # Register custom 429 error handler
    server.register_error_handler(429, _rate_limit_exceeded_handler)

    @server.context_processor
    def inject_csp_nonce():
        """Inject CSP nonce into templates for auth pages."""
        return {"csp_nonce": getattr(g, "csp_nonce", None)}

    @server.before_request
    def protect():
        # Generate CSP nonce for HTML responses
        g.csp_nonce = _generate_nonce()

        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            try:
                _, _, origin, _ = settings()
            except AuthError as error:
                return jsonify(error=error.code), error.status
            if request.headers.get("Origin") != origin:
                return jsonify(error="origin_rejected"), 403
        # The public product page never needs dashboard data or a valid session.
        # Preserve the existing root redirect for verified users.
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
                ("/_dash", "/assets/", "/api/")
            ):
                if error.status in (401, 403):
                    return redirect("/login")
                return render_template("auth.html", mode="unavailable"), 503
            return jsonify(error=GENERIC_AUTH_ERROR), error.status
        if (
            request.path == "/admin/users" or request.path.startswith("/api/admin/")
        ) and not is_admin(g.auth_user):
            if request.path.startswith("/api/"):
                return jsonify(error="admin_required"), 403
            return render_template("access_denied.html"), 403

    @server.after_request
    def private(response):
        response.headers["Cache-Control"] = "private, no-store"
        response.vary.add("Cookie")
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"

        # Add CSP header for HTML responses
        if response.content_type and response.content_type.startswith("text/html"):
            nonce = getattr(g, "csp_nonce", None)
            if nonce:
                # Runtime configuration is the only external auth connection.
                # Reject invalid source expressions rather than broadening CSP.
                configured = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
                try:
                    parsed = urlsplit(configured)
                except ValueError:
                    parsed = urlsplit("")
                connect_origin = ""
                if (
                    parsed.scheme == "https"
                    and parsed.hostname
                    and not parsed.username
                    and not parsed.password
                    and not any(c.isspace() or c in ";'\\" for c in parsed.netloc)
                ):
                    connect_origin = f" https://{parsed.netloc}"
                csp_parts = [
                    "default-src 'self'",
                    f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic'",
                    # Dash/Plotly inject styles at runtime and use style attrs.
                    # This compatibility exception applies to CSS only.
                    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net",
                    "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net",
                    f"connect-src 'self'{connect_origin}",
                    "img-src 'self' data:",
                    "object-src 'none'",
                    "frame-ancestors 'none'",
                    "base-uri 'self'",
                    "form-action 'self'",
                ]
                response.headers["Content-Security-Policy"] = "; ".join(csp_parts)

        return response

    @server.get("/auth/config")
    def config():
        try:
            url, key, _, _ = settings()
        except AuthError as error:
            return jsonify(error=error.code), error.status
        return jsonify(url=url, anonKey=key, passwordLockoutEnabled=lockout_enabled())

    @server.post("/auth/password")
    @limiter.limit("20 per minute")
    def password_login():
        if request.content_length and request.content_length > 8192:
            return jsonify(error="invalid_request"), 400
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {"email", "password"}:
            return jsonify(error="invalid_request"), 400
        try:
            tokens = password_sign_in(body["email"], body["password"])
        except PasswordAuthError as error:
            response = jsonify(error=error.code, retry_after=error.retry_after)
            response.status_code = error.status
            if error.retry_after:
                response.headers["Retry-After"] = str(error.retry_after)
            return response
        return jsonify(tokens)

    @server.get("/healthz")
    def health():
        return jsonify(status="ok")

    @server.get("/login")
    @server.get("/signup")
    @server.get("/forgot-password")
    @server.get("/reset-password")
    @server.get("/auth/callback")
    def auth_page():
        return render_template(
            "auth.html",
            mode={
                "/login": "login",
                "/signup": "signup",
                "/forgot-password": "forgot",
                "/reset-password": "reset",
            }.get(request.path, "callback"),
        )

    @server.route("/auth/session", methods=["POST", "DELETE", "GET"])
    # Count rejected attempts, not normal page loads, tab events or token refreshes.
    # Logout only clears a cookie and must remain available when throttled.
    @limiter.limit(
        "10 per minute",
        methods=["POST"],
        deduct_when=lambda response: response.status_code in (401, 403),
    )
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
            response = jsonify(
                error=(
                    "account_locked"
                    if error.code == "account_locked"
                    else GENERIC_AUTH_ERROR
                )
            )
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

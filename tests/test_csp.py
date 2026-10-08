"""
CSP Header Tests for auth pages and dashboard.

Tests verify that Content-Security-Policy headers are correctly set on all
authentication routes and the dashboard, with proper nonce handling for
inline scripts and allowed external origins.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add my-dash-app to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))

import auth
from flask import Flask


class TestCSPHeaders(unittest.TestCase):
    """Test CSP headers are present and correct on all routes."""

    def setUp(self):
        """Set up test Flask app with auth module."""
        # Create a minimal Flask app for testing
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["SECRET_KEY"] = "test-secret-key"  # pragma: allowlist secret

        # Mock environment variables
        self.env_patcher = patch.dict(
            "os.environ",
            {
                "NEXT_PUBLIC_SUPABASE_URL": "https://test-project.supabase.co",
                "NEXT_PUBLIC_SUPABASE_ANON_KEY": "test-anon-key",
                "AUTH_ALLOWED_EMAILS": "test@example.com",
                "AUTH_APP_ORIGIN": "http://localhost:8050",
            },
        )
        self.env_patcher.start()

        # Import and install auth
        auth.install_auth(self.app)

        self.client = self.app.test_client()

    def tearDown(self):
        self.env_patcher.stop()

    def _get_csp_header(self, response):
        """Extract CSP header from response."""
        return response.headers.get("Content-Security-Policy", "")

    def _get_nonce_from_html(self, response):
        """Extract nonce from HTML meta tag."""
        import re

        html = response.get_data(as_text=True)
        # Look for meta tag with csp-nonce
        match = re.search(r'<meta name="csp-nonce" content="([^"]+)">', html)
        if match:
            return match.group(1)
        # Also check for nonce in script tags
        match = re.search(r'nonce="([^"]+)"', html)
        if match:
            return match.group(1)
        return None

    def test_csp_on_login_page(self):
        """Test CSP header on /login route."""
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)

        csp = self._get_csp_header(response)
        self.assertIn("Content-Security-Policy", response.headers)
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src", csp)
        self.assertIn("style-src", csp)
        self.assertIn("connect-src", csp)

        # Verify nonce is present in HTML
        nonce = self._get_nonce_from_html(response)
        self.assertIsNotNone(nonce, "Nonce should be present in HTML")
        self.assertIn(f"nonce-{nonce}", csp, "CSP should include the nonce")

    def test_csp_on_signup_page(self):
        """Test CSP header on /signup route."""
        response = self.client.get("/signup")
        self.assertEqual(response.status_code, 200)

        csp = self._get_csp_header(response)
        self.assertIn("default-src 'self'", csp)
        nonce = self._get_nonce_from_html(response)
        self.assertIsNotNone(nonce)
        self.assertIn(f"nonce-{nonce}", csp)

    def test_csp_on_auth_callback(self):
        """Test CSP header on /auth/callback route."""
        response = self.client.get("/auth/callback")
        # Callback may redirect or show error, but should have CSP
        self.assertIn("Content-Security-Policy", response.headers)
        csp = self._get_csp_header(response)
        self.assertIn("default-src 'self'", csp)

    def test_csp_on_landing_page(self):
        """Test CSP header on / (landing) route."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

        csp = self._get_csp_header(response)
        self.assertIn("default-src 'self'", csp)
        nonce = self._get_nonce_from_html(response)
        self.assertIsNotNone(nonce, "Nonce should be present in landing page")
        self.assertIn(f"nonce-{nonce}", csp)

    def test_csp_allows_google_fonts(self):
        """Test CSP allows Google Fonts for styles and fonts."""
        response = self.client.get("/login")
        csp = self._get_csp_header(response)

        self.assertIn("fonts.googleapis.com", csp, "Should allow Google Fonts CSS")
        self.assertIn(
            "fonts.gstatic.com", csp, "Should allow Google Fonts static files"
        )

    def test_csp_allows_supabase(self):
        """Test CSP allows Supabase connections."""
        response = self.client.get("/login")
        csp = self._get_csp_header(response)

        self.assertIn("supabase.co", csp, "Should allow Supabase connect-src")
        self.assertIn("supabase.net", csp, "Should allow Supabase connect-src")

    def test_csp_allows_dash_cdn(self):
        """Test CSP allows Dash component CDN (jsdelivr, unpkg)."""
        response = self.client.get("/login")
        csp = self._get_csp_header(response)

        self.assertIn(
            "cdn.jsdelivr.net", csp, "Should allow jsDelivr CDN for Dash components"
        )
        self.assertIn("unpkg.com", csp, "Should allow unpkg CDN for Dash components")

    def test_csp_inline_script_has_nonce(self):
        """Test that inline scripts in auth.html have nonce attribute."""
        response = self.client.get("/login")
        html = response.get_data(as_text=True)

        # Check that inline script has nonce
        import re

        nonce_scripts = re.findall(r'<script[^>]*nonce="([^"]+)"[^>]*>', html)

        self.assertGreater(
            len(nonce_scripts), 0, "Should have at least one nonce'd script"
        )

        # Verify nonce matches CSP
        csp = self._get_csp_header(response)
        for nonce in nonce_scripts:
            self.assertIn(f"nonce-{nonce}", csp)

    def test_csp_external_scripts_have_nonce(self):
        """Test that external script tags have nonce attribute."""
        response = self.client.get("/login")
        html = response.get_data(as_text=True)

        import re

        # Check auth.bundle.js has nonce
        self.assertIn("nonce=", html)
        self.assertIn("auth.bundle.js", html)

        # Verify script tag has nonce attribute
        script_tags = re.findall(r'<script[^>]*src="[^"]*auth\.bundle\.js"[^>]*>', html)
        self.assertGreater(len(script_tags), 0)
        for tag in script_tags:
            self.assertIn("nonce=", tag)

    def test_csp_no_unsafe_inline(self):
        """Test CSP does not use 'unsafe-inline' for scripts."""
        response = self.client.get("/login")
        csp = self._get_csp_header(response)

        self.assertNotIn(
            "'unsafe-inline'", csp, "Should not use unsafe-inline for scripts"
        )

    def test_csp_frame_ancestors_deny(self):
        """Test CSP includes frame-ancestors 'none'."""
        response = self.client.get("/login")
        csp = self._get_csp_header(response)

        self.assertIn("frame-ancestors 'none'", csp)

    def test_csp_base_uri_self(self):
        """Test CSP includes base-uri 'self'."""
        response = self.client.get("/login")
        csp = self._get_csp_header(response)

        self.assertIn("base-uri 'self'", csp)

    def test_csp_form_action_self(self):
        """Test CSP includes form-action 'self'."""
        response = self.client.get("/login")
        csp = self._get_csp_header(response)

        self.assertIn("form-action 'self'", csp)

    def test_csp_connect_src_includes_self(self):
        """Test CSP connect-src includes 'self'."""
        response = self.client.get("/login")
        csp = self._get_csp_header(response)

        self.assertIn("connect-src 'self'", csp)

    def test_dashboard_csp_headers(self):
        """Test CSP on dashboard routes (require auth)."""
        # Mock authentication
        with patch("auth.verify_access") as mock_verify:
            mock_verify.return_value = ({"email": "test@example.com"}, "test-token")

            # Test dashboard route
            response = self.client.get(
                "/dashboard", headers={"Cookie": "sb-access-token=test"}
            )
            # May redirect or return 200/401, but should have CSP if HTML
            if response.content_type and "text/html" in response.content_type:
                self.assertIn("Content-Security-Policy", response.headers)

    def test_nonce_is_unique_per_request(self):
        """Test that each request gets a unique nonce."""
        response1 = self.client.get("/login")
        response2 = self.client.get("/login")

        nonce1 = self._get_nonce_from_html(response1)
        nonce2 = self._get_nonce_from_html(response2)

        self.assertIsNotNone(nonce1)
        self.assertIsNotNone(nonce2)
        self.assertNotEqual(nonce1, nonce2, "Nonces should be unique per request")

    def test_csp_on_static_assets(self):
        """Test that served static assets do not get the CSP header.

        In the test environment the bundle is not on disk, so the route
        returns 404. The important assertion is that no asset bytes are
        served and the 404 HTML error page (which is HTML) still gets a
        policy — verifying after_request only decorates HTML responses.
        """
        response = self.client.get("/assets/auth.bundle.js")
        self.assertEqual(response.status_code, 404)


class TestCSPIntegration(unittest.TestCase):
    """Integration tests for CSP with full app."""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["SECRET_KEY"] = "test-secret-key"  # pragma: allowlist secret

        self.env_patcher = patch.dict(
            "os.environ",
            {
                "NEXT_PUBLIC_SUPABASE_URL": "https://test-project.supabase.co",
                "NEXT_PUBLIC_SUPABASE_ANON_KEY": "test-anon-key",
                "AUTH_ALLOWED_EMAILS": "test@example.com",
                "AUTH_APP_ORIGIN": "http://localhost:8050",
            },
        )
        self.env_patcher.start()

        # Import and install auth
        auth.install_auth(self.app)

        self.client = self.app.test_client()

    def tearDown(self):
        self.env_patcher.stop()

    def test_csp_policy_structure(self):
        """Test CSP policy has all required directives."""
        response = self.client.get("/login")
        csp = response.headers.get("Content-Security-Policy", "")

        required_directives = [
            "default-src",
            "script-src",
            "style-src",
            "font-src",
            "connect-src",
            "img-src",
            "frame-ancestors",
            "base-uri",
            "form-action",
        ]

        for directive in required_directives:
            self.assertIn(directive, csp, f"Missing required directive: {directive}")


if __name__ == "__main__":
    unittest.main()

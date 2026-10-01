"""Account identity must be built separately for each authenticated request."""

import json
from pathlib import Path
import sys
import unittest

from flask import Flask, g
from plotly.utils import PlotlyJSONEncoder

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from components.sidebar import create_account_menu


class SidebarAccountTests(unittest.TestCase):
    def test_identity_is_request_scoped(self):
        server = Flask(__name__)
        for username in ("first-analyst", "second-analyst"):
            with server.test_request_context():
                g.auth_user = {
                    "email": f"{username}@example.com",
                    "user_metadata": {"username": username},
                }
                serialized = json.dumps(create_account_menu(), cls=PlotlyJSONEncoder)
                self.assertIn(username, serialized)
                other = "second-analyst" if username == "first-analyst" else "first-analyst"
                self.assertNotIn(other, serialized)

    def test_email_fallback_and_layout_without_request(self):
        server = Flask(__name__)
        with server.test_request_context():
            g.auth_user = {"email": "analyst@example.com"}
            serialized = json.dumps(create_account_menu(), cls=PlotlyJSONEncoder)
            self.assertIn("Account options for analyst", serialized)
            self.assertIn("dashboard-signout", serialized)
        serialized = json.dumps(create_account_menu(), cls=PlotlyJSONEncoder)
        self.assertIn("Account options for Account", serialized)
        self.assertNotIn("analyst@example.com", serialized)

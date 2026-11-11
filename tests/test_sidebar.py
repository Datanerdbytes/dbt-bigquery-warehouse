"""The workspace is public: the sidebar carries navigation only, no account UI."""

import json
import sys
import unittest
from pathlib import Path

from plotly.utils import PlotlyJSONEncoder

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "my-dash-app"))
from components.sidebar import create_sidebar


class SidebarPublicNavigationTests(unittest.TestCase):
    def test_sidebar_renders_public_navigation(self):
        serialized = json.dumps(create_sidebar(), cls=PlotlyJSONEncoder)
        for href in ("/dashboard", "/customers", "/pipeline-health"):
            self.assertIn(href, serialized)

    def test_sidebar_has_no_account_or_admin_artifacts(self):
        """Regression: removing authentication removed the account menu and the
        admin link; neither may come back through the shared sidebar."""
        serialized = json.dumps(create_sidebar(), cls=PlotlyJSONEncoder)
        self.assertNotIn("sidebar-account", serialized)
        self.assertNotIn("dashboard-signout", serialized)
        self.assertNotIn("/admin/users", serialized)


if __name__ == "__main__":
    unittest.main()

"""WSGI entrypoint for the Vercel Python runtime.

The Dash application lives in ``my-dash-app/``. That directory name contains a
hyphen, so it cannot be imported as a package; it is placed on ``sys.path``
instead and the application module is imported from there. The imported module
resolves to ``my-dash-app/app.py``, which is what Dash uses to locate the
``assets`` and ``pages`` folders.

Vercel requires the WSGI callable to be named ``app``.
"""

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent / "my-dash-app"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from app import server  # noqa: E402

app = server

"""Cold-process regression for concurrent Plotly template initialization."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ChartStartupTests(unittest.TestCase):
    def test_concurrent_first_charts_preserve_templates_without_errors(self):
        # A new interpreter avoids template caches warmed by other tests.
        # Slow template Bar construction widens the actual race window; the
        # uninitialized implementation raises the CI's ValueError reliably.
        script = r"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import plotly.express as px
import plotly.io as pio
from plotly.graph_objs import Bar
sys.path.insert(0, "my-dash-app")
from theme import initialize_chart_templates, style_figure

before = {name: pio.templates[name].to_plotly_json()
          for name in ("plotly", "plotly_dark")}
original = Bar.__init__
def delayed_init(self, *args, **kwargs):
    if kwargs.get("_parent") is not None:
        time.sleep(0.03)
    original(self, *args, **kwargs)
Bar.__init__ = delayed_init
initialize_chart_templates()
assert pio.templates.default == "plotly"
for name, value in before.items():
    assert pio.templates[name].to_plotly_json() == value

barrier = Barrier(16)
def render(i):
    barrier.wait(timeout=10)
    chart = (px.area, px.bar, px.scatter, px.line)[i % 4]
    fig = style_figure(chart(x=[1, 2], y=[2, 3]))
    assert list(fig.data[0].y) == [2, 3]
    assert fig.layout.template.to_plotly_json() == before["plotly_dark"]
    return fig.to_json()
with ThreadPoolExecutor(16) as pool:
    assert all(pool.map(render, range(16)))
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

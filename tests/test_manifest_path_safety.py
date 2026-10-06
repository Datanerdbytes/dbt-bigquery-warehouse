import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics_layer.scripts import calculate_coverage as coverage_module
from analytics_layer.scripts.calculate_coverage import (
    load_manifest as coverage_load_manifest,
)


def test_load_manifest_valid_path(tmp_path, monkeypatch):
    manifest = {"nodes": {}}
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    monkeypatch.setattr(coverage_module, "MANIFEST_PATH", manifest_file)
    monkeypatch.setattr(coverage_module, "ALLOWED_MANIFEST_ROOT", tmp_path)

    result = coverage_load_manifest()
    assert result == manifest


def test_load_manifest_missing_path_does_not_leak_path(tmp_path, monkeypatch):
    missing = tmp_path / "manifest.json"
    monkeypatch.setattr(coverage_module, "MANIFEST_PATH", missing)
    monkeypatch.setattr(coverage_module, "ALLOWED_MANIFEST_ROOT", tmp_path)

    with pytest.raises(FileNotFoundError) as exc_info:
        coverage_load_manifest()

    assert str(missing) not in str(exc_info.value)


def test_load_manifest_traversal_outside_target_does_not_leak_path(
    tmp_path, monkeypatch
):
    traversal = tmp_path / ".." / "secret.txt"
    monkeypatch.setattr(coverage_module, "MANIFEST_PATH", traversal)
    monkeypatch.setattr(coverage_module, "ALLOWED_MANIFEST_ROOT", tmp_path)

    with pytest.raises(ValueError) as exc_info:
        coverage_load_manifest()

    assert "secret.txt" not in str(exc_info.value)


def test_load_manifest_invalid_json_does_not_leak_path(tmp_path, monkeypatch):
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text("not-json")

    monkeypatch.setattr(coverage_module, "MANIFEST_PATH", manifest_file)
    monkeypatch.setattr(coverage_module, "ALLOWED_MANIFEST_ROOT", tmp_path)

    with pytest.raises(RuntimeError) as exc_info:
        coverage_load_manifest()

    assert "not-json" not in str(exc_info.value)


def _run_observability_snippet(code: str):
    import subprocess
    import textwrap

    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result


def test_observability_load_manifest_missing_returns_empty():
    helper = f"""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(r"{ROOT}")

for name in list(sys.modules):
    if name == "dash" or name.startswith("dash.") or name.startswith("dash_bootstrap") or name.startswith("plotly") or name.startswith("pandas") or name.startswith("google.cloud") or name == "google" or name == "data_loader":
        del sys.modules[name]

dash = ModuleType("dash")
dash.register_page = lambda *args, **kwargs: None

dash_html = ModuleType("dash.html")
dash_html.Div = lambda *args, **kwargs: None
dash_html.H2 = lambda *args, **kwargs: None

dash_dcc = ModuleType("dash.dcc")
dash_dcc.Store = lambda *args, **kwargs: None
dash_dcc.Interval = lambda *args, **kwargs: None

dash.html = dash_html
dash.dcc = dash_dcc
dash.callback = lambda *args, **kwargs: lambda f: f
dash.Input = lambda *args, **kwargs: None
dash.Output = lambda *args, **kwargs: None
dash.State = lambda *args, **kwargs: None
dash.no_update = None
dash.exceptions = ModuleType("dash.exceptions")

dash_development = ModuleType("dash.development")
dash_development_base = ModuleType("dash.development.base_component")
dash_development_base.Component = type("Component", (), {{}})
dash_development_base._explicitize_args = lambda f: f

dash_bootstrap = ModuleType("dash_bootstrap_components")
dash_bootstrap.Container = lambda *args, **kwargs: None
dash_bootstrap.Row = lambda *args, **kwargs: None
dash_bootstrap.Col = lambda *args, **kwargs: None

dash_ag_grid = ModuleType("dash_ag_grid")
dash_ag_grid.AgGrid = lambda *args, **kwargs: None

plotly_go = ModuleType("plotly.graph_objects")
plotly_go.Figure = object

pandas = ModuleType("pandas")
pandas.DataFrame = object

bigquery = ModuleType("google.cloud.bigquery")
bigquery.Client = object

google = ModuleType("google")
google.cloud = ModuleType("google.cloud")
google.cloud.bigquery = bigquery

data_loader = ModuleType("data_loader")
data_loader.get_bigquery_client = lambda: None
data_loader.load_pipeline_health_summary = lambda *a, **k: None
data_loader.load_dbt_execution_logs = lambda *a, **k: None

stubs = {{
    "dash": dash,
    "dash.html": dash_html,
    "dash.dcc": dash_dcc,
    "dash.exceptions": dash.exceptions,
    "dash.development": dash_development,
    "dash.development.base_component": dash_development_base,
    "dash_bootstrap_components": dash_bootstrap,
    "dash_ag_grid": dash_ag_grid,
    "plotly.graph_objects": plotly_go,
    "pandas": pandas,
    "google.cloud.bigquery": bigquery,
    "google": google,
    "google.cloud": google.cloud,
    "data_loader": data_loader,
}}
for name, module in stubs.items():
    sys.modules[name] = module

spec = importlib.util.spec_from_file_location("app_observability", ROOT / "my-dash-app" / "app_observability.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

mod.MANIFEST_PATH = Path("/nonexistent/target/manifest.json")
mod.ALLOWED_MANIFEST_ROOT = Path("/nonexistent/target")
mod.load_manifest.cache_clear()
assert mod.load_manifest() == {{}}
print("ok")
    """
    result = _run_observability_snippet(helper)
    assert result.returncode == 0, result.stdout + result.stderr


def test_observability_load_manifest_invalid_json_returns_empty(tmp_path):
    helper = f"""
import importlib.util
import sys
import tempfile
from pathlib import Path
from types import ModuleType

ROOT = Path(r"{ROOT}")

for name in list(sys.modules):
    if name == "dash" or name.startswith("dash.") or name.startswith("dash_bootstrap") or name.startswith("plotly") or name.startswith("pandas") or name.startswith("google.cloud") or name == "google" or name == "data_loader":
        del sys.modules[name]

dash = ModuleType("dash")
dash.register_page = lambda *args, **kwargs: None

dash_html = ModuleType("dash.html")
dash_html.Div = lambda *args, **kwargs: None
dash_html.H2 = lambda *args, **kwargs: None

dash_dcc = ModuleType("dash.dcc")
dash_dcc.Store = lambda *args, **kwargs: None
dash_dcc.Interval = lambda *args, **kwargs: None

dash.html = dash_html
dash.dcc = dash_dcc
dash.callback = lambda *args, **kwargs: lambda f: f
dash.Input = lambda *args, **kwargs: None
dash.Output = lambda *args, **kwargs: None
dash.State = lambda *args, **kwargs: None
dash.no_update = None
dash.exceptions = ModuleType("dash.exceptions")

dash_development = ModuleType("dash.development")
dash_development_base = ModuleType("dash.development.base_component")
dash_development_base.Component = type("Component", (), {{}})
dash_development_base._explicitize_args = lambda f: f

dash_bootstrap = ModuleType("dash_bootstrap_components")
dash_bootstrap.Container = lambda *args, **kwargs: None
dash_bootstrap.Row = lambda *args, **kwargs: None
dash_bootstrap.Col = lambda *args, **kwargs: None

dash_ag_grid = ModuleType("dash_ag_grid")
dash_ag_grid.AgGrid = lambda *args, **kwargs: None

plotly_go = ModuleType("plotly.graph_objects")
plotly_go.Figure = object

pandas = ModuleType("pandas")
pandas.DataFrame = object

bigquery = ModuleType("google.cloud.bigquery")
bigquery.Client = object

google = ModuleType("google")
google.cloud = ModuleType("google.cloud")
google.cloud.bigquery = bigquery

data_loader = ModuleType("data_loader")
data_loader.get_bigquery_client = lambda: None
data_loader.load_pipeline_health_summary = lambda *a, **k: None
data_loader.load_dbt_execution_logs = lambda *a, **k: None

stubs = {{
    "dash": dash,
    "dash.html": dash_html,
    "dash.dcc": dash_dcc,
    "dash.exceptions": dash.exceptions,
    "dash.development": dash_development,
    "dash.development.base_component": dash_development_base,
    "dash_bootstrap_components": dash_bootstrap,
    "dash_ag_grid": dash_ag_grid,
    "plotly.graph_objects": plotly_go,
    "pandas": pandas,
    "google.cloud.bigquery": bigquery,
    "google": google,
    "google.cloud": google.cloud,
    "data_loader": data_loader,
}}
for name, module in stubs.items():
    sys.modules[name] = module

spec = importlib.util.spec_from_file_location("app_observability", ROOT / "my-dash-app" / "app_observability.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp) / "manifest.json"
    p.write_text("not-json")
    mod.MANIFEST_PATH = p
    mod.ALLOWED_MANIFEST_ROOT = Path(tmp)
    mod.load_manifest.cache_clear()
    assert mod.load_manifest() == {{}}
print("ok")
"""
    result = _run_observability_snippet(helper)
    assert result.returncode == 0, result.stdout + result.stderr

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

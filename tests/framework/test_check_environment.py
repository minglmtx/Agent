"""Frozen environment identity changes when declared runtime inputs change."""

import importlib.metadata
import sys
from pathlib import Path
import pytest
from framework_checks import environment
from framework_checks.cache import digest


@pytest.mark.parametrize(
    "change", ["metadata", "record", "python", "pythonpath", "mypy"]
)
def test_runtime_identity_detects_changed_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    metadata = tmp_path / "example-1.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text("Name: example\nVersion: 1\n")
    (metadata / "RECORD").write_text("original")
    distribution = importlib.metadata.PathDistribution(metadata)
    monkeypatch.setattr(importlib.metadata, "distributions", lambda: [distribution])
    python = tmp_path / "python"
    python.write_bytes(b"runtime")
    monkeypatch.setattr(sys, "executable", str(python))
    external = tmp_path / "tools"
    (external / "mypy").mkdir(parents=True)
    (external / "mypy/__init__.py").write_text("original")
    monkeypatch.setenv("PYTHONPATH", str(external))
    original = environment.environment_identity()
    assert digest(environment.environment_identity()) == digest(original)
    if change == "metadata":
        (metadata / "METADATA").write_text("Name: example\nVersion: 2\n")
    if change == "record":
        (metadata / "RECORD").write_text("new")
    if change == "python":
        python.write_bytes(b"new-runtime")
    if change == "pythonpath":
        monkeypatch.setenv("PYTHONPATH", str(tmp_path / "different"))
    if change == "mypy":
        (external / "mypy/__init__.py").write_text("new")
    assert digest(environment.environment_identity()) != digest(original)

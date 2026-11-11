"""Original baseline and private controls, failure retention and capsule parity."""

import ast
import hashlib
import json
import math
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
import pytest
from lab_generate_skill.adapters.map_runtime.layout import NativeMapLayout, baseline
from lab_generate_skill.adapters.map_runtime import layout
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.sites.map.service_controls import (
    controls,
    POSTGRES,
    SEARCH_ROUTER,
    RENDERD,
    APACHE,
    sample_tile_path,
)
from lab_generate_skill.sites.map.tile_style import private_style
from map_services_fixtures import selected, cloned, replace_source, STYLE
from map_database_original_oracle import ROOT, CAPSULE
from site_instance_fixtures import node_path
from test_slurm_commands import guard


def test_original_capsule_settings_and_mapnik_rule_parity(tmp_path: Path) -> None:
    raw = CAPSULE.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "3c537fffffcf2768fc3bcedb4e567ed39565f76faf01f3b1f685614d35e724f5"
    )
    pins = json.loads(raw)["members"]
    bodies = {}
    for name in ("map_query_site", "map_tiles"):
        relative = "src/lab_generate_skill/" + name + ".py"
        body = (ROOT / relative).read_bytes()
        assert hashlib.sha256(body).hexdigest() == pins[relative]["sha256"]
        bodies[name] = ast.parse(body)
    constants = [
        n.value
        for tree in bodies.values()
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and type(n.value) is str
    ]
    for text in (POSTGRES, SEARCH_ROUTER, RENDERD, APACHE):
        assert text in constants
    functions = [
        n
        for n in bodies["map_tiles"].body
        if isinstance(n, ast.FunctionDef)
        and n.name in ("rebind_mapnik_database", "sample_tile_path")
    ]
    namespace: dict[str, Any] = {"ET": ET, "math": math}
    exec(
        compile(
            ast.Module(body=list[ast.stmt](functions), type_ignores=[]),
            "original-map-tiles-pure",
            "exec",
        ),
        namespace,
    )
    assert sample_tile_path() == namespace["sample_tile_path"]()
    original = tmp_path / "mapnik.xml"
    original.write_bytes(STYLE)
    namespace["rebind_mapnik_database"](original)
    assert ET.tostring(ET.fromstring(private_style(STYLE))) == ET.tostring(
        ET.parse(original).getroot()
    )


def test_baseline_and_private_controls_original_pid_cleanup(node_path: Path) -> None:
    spec = selected(node_path)
    cloned(spec)
    private_pid = Path(spec.inputs.node_tree("search")) / "postgres/postmaster.pid"
    private_pid.write_text("historical copied pid\n")
    content = controls(spec, hostname="native-node", host_cpus=128)
    assert baseline(spec, guard())["full_snapshot_imported"] is True
    removed = NativeMapLayout().prepare(spec, content, guard())
    assert removed == (str(private_pid),) and not private_pid.exists()
    root = Path(spec.inputs.files.state_root)
    for name, expected in content.items():
        assert (root / name).read_text() == expected
        assert (root / name).stat().st_mode & 0o777 == 0o600
    assert "ModTileMaxLoadMissing 128" in (root / "tiles/apache.conf").read_text()
    assert "AddTileConfig" not in (root / "tiles/apache.conf").read_text()
    assert "num_threads=2" in (root / "tiles/renderd.conf").read_text()
    with pytest.raises(EvidenceIntegrityError):
        NativeMapLayout().prepare(spec, content, guard())


@pytest.mark.parametrize(
    "change", ["version", "incomplete", "snapshot", "object", "offline", "alias"]
)
def test_baseline_failure_before_control_creation(node_path: Path, change: str) -> None:
    spec = selected(node_path)
    plan = spec.inputs
    if change == "version":
        plan = replace_source(plan, "search", "postgres/PG_VERSION", b"15\n")
    elif change in ("incomplete", "snapshot", "object"):
        declaration = next(t for t in plan.trees if t.role == "app")
        metadata = json.loads(
            (Path(declaration.source_root) / "baseline.json").read_text()
        )
        if change == "incomplete":
            metadata["status"] = "pending"
        elif change == "snapshot":
            metadata["full_snapshot_imported"] = 1
        else:
            metadata["object_checks"]["way"]["id"] = 0
        plan = replace_source(
            plan, "app", "baseline.json", json.dumps(metadata).encode()
        )
    spec = MapServiceSpec.model_validate({**spec.model_dump(), "inputs": plan})
    cloned(spec)
    if change == "offline":
        (Path(plan.node_tree("app")) / "postgres/postmaster.pid").write_text("pid")
    elif change == "alias":
        original = Path(plan.node_tree("app")) / "baseline.json"
        target = original.with_suffix(".saved")
        original.rename(target)
        original.symlink_to(target)
    with pytest.raises(EvidenceIntegrityError):
        NativeMapLayout().prepare(
            spec, controls(spec, hostname="node", host_cpus=1), guard()
        )
    assert not list(Path(plan.files.state_root).iterdir())


@pytest.mark.parametrize(
    "host,cpus",
    [
        ("node\n127.0.0.2 evil", 8),
        ("", 1),
        (None, 8),
        ("node", True),
        ("node", 0),
        ("node", "128"),
    ],
)
def test_invalid_observed_host_configuration(
    node_path: Path, host: Any, cpus: Any
) -> None:
    spec = selected(node_path)
    with pytest.raises(ValueError):
        controls(spec, hostname=host, host_cpus=cpus)


def test_cancelled_partial_layout_cannot_resume(node_path: Path) -> None:
    spec = selected(node_path)
    cloned(spec)
    root = Path(spec.inputs.files.state_root)

    class Stop:
        def checkpoint(self) -> float:
            if (root / "search").exists():
                raise TimeoutError("original layout cancellation")
            return 10.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    content = controls(spec, hostname="node", host_cpus=1)
    with pytest.raises(TimeoutError):
        NativeMapLayout().prepare(spec, content, Stop())
    assert (root / "search").is_dir() and not (root / "tiles").exists()
    with pytest.raises(EvidenceIntegrityError):
        NativeMapLayout().prepare(spec, content, guard())


def test_control_sync_failure_retains_partial_files(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = selected(node_path)
    cloned(spec)
    content = controls(spec, hostname="node", host_cpus=1)
    failure = OSError("original configuration fsync failed")

    def fail(path: Path) -> None:
        raise failure

    monkeypatch.setattr(layout, "sync_regular_file", fail)
    with pytest.raises(OSError) as caught:
        NativeMapLayout().prepare(spec, content, guard())
    assert caught.value is failure
    assert (Path(spec.state_root("search")) / "hosts").read_text() == content[
        "search/hosts"
    ]
    with pytest.raises(EvidenceIntegrityError):
        NativeMapLayout().prepare(spec, content, guard())


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"<Map/>",
        b"<Other/>",
        b"broken",
        b"<!DOCTYPE Map><Map/>",
        b'<Map><Datasource><Parameter name="type">postgis</Parameter><Parameter name="type">postgis</Parameter></Datasource></Map>',
    ],
)
def test_invalid_native_style_rejected(raw: bytes) -> None:
    with pytest.raises((ValueError, ET.ParseError)):
        private_style(raw)

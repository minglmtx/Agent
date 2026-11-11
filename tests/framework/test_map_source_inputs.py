"""Actual pinned metadata, declaration-only planning and original preparation ports.

No images/trees are recopied or fully rehashed; no service, browser or Actor starts.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any
from collections.abc import Iterator
import os
import tempfile
import pytest
from evidence_control_fixtures import EvidenceFixtureStore
from map_source_inputs import (
    source_inputs,
    public_task,
    RUNTIME_PATH,
    W,
    engineering_scope,
)
from map_preparation_native import MapPreparation
from lab_generate_skill.domain.site_worker import (
    SiteInstanceStarted,
    SiteWorkerConfiguration,
)
from lab_generate_skill.domain.errors import OperationStopped, EvidenceIntegrityError
from site_worker_fixtures import configuration
from site_resource_fixtures import resource_case
from test_slurm_commands import guard

SourceCase = tuple[Path, Path, Path, SiteWorkerConfiguration, EvidenceFixtureStore]


@pytest.fixture
def source_case(tmp_path: Path) -> Iterator[SourceCase]:
    root = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / (
        "actual-map-input-" + tmp_path.name
    )
    root.mkdir(mode=0o700)
    evidence = root / "shared-evidence"
    evidence.mkdir(mode=0o700)
    parent = Path(tempfile.mkdtemp(prefix="map-input-declaration-", dir="/tmp"))
    base = configuration(job_id=os.environ["SLURM_JOB_ID"])
    store = EvidenceFixtureStore(evidence)
    try:
        yield root, evidence, parent, base, store
    finally:
        assert not list(
            parent.iterdir()
        )  # Declaration must not create a native instance.
        parent.rmdir()


def test_actual_original_metadata_repeated_plan_and_preparation_binding(
    source_case: SourceCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, evidence, parent, base, store = source_case
    site_root = root / "site"
    site_root.mkdir(mode=0o700)
    value = source_inputs(
        store,
        base.token.owner,
        base.installation,
        site_root,
        parent,
        guard(),
        scope=engineering_scope(base.token.owner, None),
        evidence_root=evidence,
    )
    assert (
        source_inputs(
            store,
            base.token.owner,
            base.installation,
            site_root,
            parent,
            guard(),
            scope=engineering_scope(base.token.owner, None),
            evidence_root=evidence,
        )
        == value
    )
    cfg = value.configuration
    assert (
        cfg.map_inputs is not None
        and cfg.map_inputs.runtime.publication_job_id == "4795725"
    )
    assert (
        cfg.files.node_root == str(parent / "instance")
        and not Path(cfg.files.node_root).exists()
    )
    assert cfg.map_inputs.evidence_root == str(evidence)
    assert cfg.map_inputs.max_file_bytes > 64 * 1024**2
    assert value.original_sources is not None
    assert value.original_sources.root == str(
        W / "assets/map-native-overlay-20261029-v1/frontend"
    )
    c = resource_case(site_root, monkeypatch, config=cfg, store=store)
    # Factory's generic close-only fixture recovery is not Map environment recovery.
    # Restore the predeclared exact source before any acquisition is registered.
    c.spec = c.spec.model_copy(update={"configuration": cfg})
    c.op = c.op.model_copy(update={"recovery_ref": cfg.token.recovery_ref})
    started = SiteInstanceStarted(
        files=cfg.files,
        endpoint="http://127.0.0.1:18080/",
        ports=(18080, 18081, 18082, 18083, 18084, 18085),
    )
    prepared = MapPreparation(
        c, started, value, allowed_actions=("click", "send_msg_to_user")
    )
    assert prepared.bindings.load(prepared.binding_ref, c.op) == prepared.binding
    assert prepared.private_input_json() == value.private.model_dump_json()
    assert prepared.public.start_url.startswith(started.endpoint + "directions?")
    assert prepared.spec_ref == value.state_spec_ref
    assert c.channels == []
    again = MapPreparation(
        c, started, value, allowed_actions=("click", "send_msg_to_user")
    )
    assert again.binding_ref == prepared.binding_ref
    with pytest.raises(ValueError, match="pin changed"):
        MapPreparation(
            c,
            started,
            replace(
                value,
                private=value.private.model_copy(update={"native_goal": "changed"}),
            ),
            allowed_actions=("click", "send_msg_to_user"),
        )
    assert not list(parent.iterdir()) and c.channels == []


@pytest.mark.parametrize(
    "fault",
    [
        "outside",
        "workspace-root",
        "node-root",
        "wrong-type",
        "cancel",
        "metadata-bytes",
        "metadata-link",
    ],
)
def test_no_dispatch_with_invalid_paths_cancellation_or_changed_metadata(
    source_case: SourceCase, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    root, evidence, parent, base, store = source_case
    site_root: Any = root / "site"
    node_root: Any = parent
    control = guard()
    if fault == "outside":
        site_root = Path("/tmp/other-controls")
    if fault == "workspace-root":
        site_root = W
    if fault == "node-root":
        node_root = Path("/tmp")
    if fault == "wrong-type":
        node_root = "not-a-path"
    if fault == "cancel":
        control = guard(-1)
    if fault in ("metadata-bytes", "metadata-link"):
        path = root / "runtime-inputs.json"
        if fault == "metadata-link":
            path.symlink_to(RUNTIME_PATH)
        else:
            path.write_bytes(RUNTIME_PATH.read_bytes() + b" ")
        monkeypatch.setattr("map_source_inputs.RUNTIME_PATH", path)
    with pytest.raises(
        (ValueError, TypeError, OperationStopped, EvidenceIntegrityError)
    ):
        source_inputs(
            store,
            base.token.owner,
            base.installation,
            site_root,
            node_root,
            control,
            scope=engineering_scope(base.token.owner, None),
            evidence_root=evidence,
        )
    assert not list(parent.iterdir())


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        None,
        True,
        [],
        "http://localhost:18080/",
        "http://127.0.0.1:80/",
        "http://127.0.0.1:65536/",
        "http://127.0.0.1:18080/submit",
        "http://127.0.0.1:18080/?x=1",
        "http://user@127.0.0.1:18080/",
    ],
)
def test_exact_allocated_original_route_start(endpoint: Any) -> None:
    with pytest.raises((ValueError, TypeError)):
        public_task(endpoint, ("click", "send_msg_to_user"))

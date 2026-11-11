"""Complete original files and selected preparation semantics; native/OS are doubles."""

import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.map_overlay_records import (
    map_original_state_reader,
    map_prepared_browser_checks,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.sites.map.state_fact import complete_state
from lab_generate_skill.sites.map.tasks.overlay_recovery import OverlayObserved
from map_registered_worker_fixtures import RegisteredMapCase
from map_prepared_records_fixtures import prepare
from preparation_record_fixtures import put
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_site_resource import enter
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    ["none", "request", "descriptor", "missing", "corrupt", "permission", "cancel"],
)
def test_original_complete_reader_and_preparation(
    fault: str, registered_map: RegisteredMapCase
) -> None:
    c = registered_map
    with enter(c.resource) as registered:
        p = prepare(c, registered)
        assert p.environment.checks.status == "unknown"
        c.observer = "controller"
        try:
            reader = map_original_state_reader(
                c.configuration, registered.site.instance
            )
            native, request = p.observed.native, p.request
            if fault == "request":
                request = request.model_copy(
                    update={
                        "operation": request.operation.model_copy(
                            update={"operation_id": "other"}
                        )
                    }
                )
            if fault == "descriptor":
                native = native.model_copy(
                    update={"file": native.file.model_copy(update={"sha256": "f" * 64})}
                )
            # Use the actual manifest root rather than assuming storage layout.
            manifest = json.loads(
                (
                    Path(native.plan.private_root) / "published/manifest.json"
                ).read_bytes()
            )
            path = Path(manifest["artifact"]["root"]) / "state.json"
            if fault == "missing":
                path.parent.chmod(0o700)
                path.unlink()
            if fault == "corrupt":
                path.chmod(0o600)
                path.write_bytes(b"corrupt")
            if fault == "permission":
                c.member_change["user_inode"] = 1

            class Cancel:
                def checkpoint(self) -> float:
                    raise OperationStopped("CANCELLED", "original-map-state")

                def wait(self, seconds: float) -> None:
                    self.checkpoint()

            if fault == "none":
                raw = reader.read(native, request, guard())
                assert (
                    complete_state(raw, native, request).sha256
                    == p.snapshot.native.state_sha256
                )
                assert reader.read(native, request, guard()) == raw
                assert p.records.load(p.publication, request.operation).scope == c.scope
            elif fault == "cancel":
                with pytest.raises(OperationStopped):
                    reader.read(native, request, Cancel())
            else:
                with pytest.raises(
                    (
                        ValueError,
                        OwnershipConflict,
                        EvidenceIntegrityError,
                        FileNotFoundError,
                    )
                ):
                    reader.read(native, request, guard())
        finally:
            c.observer = "worker"
            c.member_change.clear()


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "endpoint",
        "instance",
        "configuration",
        "result",
        "snapshot",
        "native-hash",
    ],
)
def test_selected_browser_check_reads_original_snapshot_and_prepare(
    fault: str, registered_map: RegisteredMapCase
) -> None:
    c = registered_map
    with enter(c.resource) as registered:
        p = prepare(c, registered)
        c.observer = "controller"
        try:
            cfg, instance = c.configuration, registered.site.instance
            checks = map_prepared_browser_checks(c.resource.evidence, cfg, instance)
            selected = MapNativeInitialization(
                endpoint=instance.endpoint,
                prepared_ref=p.publication.prepared_ref,
                site_ref=put(c.resource.evidence, registered.site),
            )
            result, request = p.result, p.request
            if fault == "endpoint":
                selected = selected.model_copy(
                    update={"endpoint": "http://127.0.0.1:65535/"}
                )
            if fault == "instance":
                instance = instance.model_copy(
                    update={
                        "files": instance.files.model_copy(
                            update={"instance_id": "other"}
                        )
                    }
                )
            if fault == "configuration":
                assert cfg.map_inputs is not None
                cfg = cfg.model_copy(
                    update={
                        "map_inputs": cfg.map_inputs.model_copy(
                            update={"private_input_sha256": "f" * 64}
                        )
                    }
                )
            if fault == "result":
                result = result.model_copy(update={"request_sha256": "f" * 64})
            if fault == "snapshot":
                request = request.model_copy(
                    update={"snapshot_ref": c.put(b"{}", "map-overlay-snapshot/1")}
                )
                result = result.model_copy(update={"request_sha256": request.digest})
            if fault == "native-hash":
                observed = p.observed.model_copy(
                    update={
                        "native": p.observed.native.model_copy(
                            update={
                                "file": p.observed.native.file.model_copy(
                                    update={"sha256": "f" * 64}
                                )
                            }
                        )
                    }
                )
                result = SiteTaskResult(
                    request_sha256=request.digest,
                    private_result=observed.model_dump_json(),
                )
            ref = put(c.resource.evidence, result)
            if fault == "none":
                checks.check_prepared(ref, request, selected, cfg, instance, guard())
                checks.check_prepared(ref, request, selected, cfg, instance, guard())
            else:
                with pytest.raises(
                    (ValueError, EvidenceIntegrityError, OwnershipConflict)
                ):
                    checks.check_prepared(
                        ref, request, selected, cfg, instance, guard()
                    )
        finally:
            c.observer = "worker"


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "null",
        "list",
        "type",
        "extra",
        "duplicate",
        "request",
        "sha",
        "dirty",
        "sql-type",
        "persistent-type",
        "incomplete",
        "noncanonical",
    ],
)
def test_full_guard_record_cannot_hide_malformed_or_dirty_state(
    fault: str, registered_map: RegisteredMapCase
) -> None:
    c = registered_map
    with enter(c.resource) as registered:
        p = prepare(c, registered)
        c.observer = "controller"
        try:
            native = p.observed.native
            raw: Any = map_original_state_reader(
                c.configuration, registered.site.instance
            ).read(native, p.request, guard())
            value = json.loads(raw)
            if fault == "empty":
                raw = b""
            elif fault == "null":
                raw = b"null"
            elif fault == "list":
                raw = b"[]"
            elif fault == "type":
                raw = "wrong"
            elif fault == "duplicate":
                raw = b'{"sha256":"first",' + raw[1:]
            else:
                if fault == "extra":
                    value["extra"] = 1
                if fault == "request":
                    value["request_sha256"] = "f" * 64
                if fault == "sha":
                    value["sha256"] = "f" * 64
                if fault == "sql-type":
                    value["database"] = []
                if fault == "persistent-type":
                    value["persistent"] = []
                if fault == "incomplete":
                    value.pop("persistent")
                if fault == "dirty":
                    sql = json.loads(value["database"])
                    sql["changed"] = ["public." + sql["tables"][0]]
                    value["database"] = json.dumps(sql)
                raw = json.dumps(
                    value, sort_keys=True, indent=2 if fault == "noncanonical" else None
                ).encode()
            if type(raw) is bytes and raw:
                native = native.model_copy(
                    update={
                        "file": native.file.model_copy(
                            update={
                                "size_bytes": len(raw),
                                "sha256": hashlib.sha256(raw).hexdigest(),
                            }
                        )
                    }
                )
            with pytest.raises((ValueError, EvidenceIntegrityError)):
                complete_state(raw, native, p.request)
        finally:
            c.observer = "worker"


@pytest.mark.parametrize(
    "fault", ["environment", "public", "coverage", "recovery", "private"]
)
def test_preparation_checks_keep_environment_and_binding_boundaries(
    fault: str, registered_map: RegisteredMapCase
) -> None:
    c = registered_map
    with enter(c.resource) as registered:
        p = prepare(c, registered)
        c.observer = "controller"
        try:
            inputs = p.records.reader.load(
                p.publication.selection, p.request.operation, guard()
            )
            if fault == "environment":
                inputs = inputs.model_copy(
                    update={
                        "environment": inputs.environment.model_copy(
                            update={"measured_state_sha256": "f" * 64}
                        )
                    }
                )
            if fault == "public":
                inputs = inputs.model_copy(
                    update={
                        "public_task": inputs.public_task.model_copy(
                            update={"goal": "other"}
                        )
                    }
                )
            if fault == "coverage":
                inputs = inputs.model_copy(
                    update={
                        "spec": inputs.spec.model_copy(
                            update={"preparation_checks": ("other",)}
                        )
                    }
                )
            if fault == "recovery":
                inputs = inputs.model_copy(
                    update={
                        "recovery": inputs.recovery.model_copy(
                            update={"restore_component_version": "other"}
                        )
                    }
                )
            if fault == "private":
                other = c.private.model_copy(
                    update={
                        "native_contract_ref": c.private.native_contract_ref.model_copy(
                            update={"producer": "other"}
                        )
                    }
                )
                inputs = inputs.model_copy(
                    update={
                        "binding": inputs.binding.model_copy(
                            update={"private_spec_ref": put(c.resource.evidence, other)}
                        )
                    }
                )
            with pytest.raises((ValueError, OwnershipConflict)):
                p.records.checks.check(inputs, guard())
        finally:
            c.observer = "worker"

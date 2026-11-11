"""Actual pending producer intent -> original authority -> mandatory site codec.

The physical resource gate is a deliberate stop boundary, never a permission
fixture. No native dispatch, source replay, service or Actor is performed.
"""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.errors import OwnershipConflict
from admin_navigation_owned_fixtures import owned_navigation_case
from test_admin_navigation_input import contracts as contracts
from test_gitlab_group_owned_bindings import group_owned as group_owned
from map_task_execution_current_fixtures import current_map_execution_case
from map_navigation_group_cases import SOURCES
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


class PhysicalGateReached(Exception):
    pass


def check_original_pending_snapshot(
    bundle: Any, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    p, a = bundle.preparation, bundle.native_authority
    control = guard()
    request = SiteTaskRequest(
        task=p.declaration.scope.task,
        binding_ref=p.declaration.task_binding_ref,
        operation=p.declaration.snapshot_operation,
        action="snapshot",
        private_input=p.io.read(p.declaration.private_input_ref, control).decode(),
    )
    # These are exactly the current producer fields before _dispatch sends its
    # first request. The current intent is not a previously returned snapshot.
    p.state.phase = "preparing"
    p.state.snapshot_request = request
    p.state.snapshot_request_ref = p.io.put(request, control)
    binding = TaskBinding.model_validate_json(
        p.io.read(p.declaration.task_binding_ref, control)
    )
    private_refs = {p.declaration.private_input_ref, binding.private_spec_ref}
    body_reads = []
    original_read = p.io.read

    def counted_read(reference: Any, local: Any) -> bytes:
        body_reads.append(reference)
        raw = original_read(reference, local)
        if type(raw) is not bytes:
            raise TypeError("Original preparation evidence must return bytes")
        return raw

    monkeypatch.setattr(p.io, "read", counted_read)
    calls: list[tuple[bytes | None, SiteTaskRequest | None]] = []
    original = a.inputs.verify_inputs

    def observed(
        configuration: Any,
        selected: Any,
        binding: Any,
        recovery: Any,
        environment: Any,
        snapshot_bytes: Any,
        snapshot_request: Any,
        local: Any,
    ) -> None:
        calls.append((snapshot_bytes, snapshot_request))
        original(
            configuration,
            selected,
            binding,
            recovery,
            environment,
            snapshot_bytes,
            snapshot_request,
            local,
        )

    def stop_before_physical(selected: Any, local: Any) -> Any:
        assert selected == request
        local.checkpoint()
        raise PhysicalGateReached

    monkeypatch.setattr(a.inputs, "verify_inputs", observed)
    monkeypatch.setattr(a, "_resource", stop_before_physical)
    if fault == "intent_producer":
        p.state.snapshot_request_ref = p.state.snapshot_request_ref.model_copy(
            update={"producer": "foreign"}
        )
    elif fault == "intent_changed":
        p.state.snapshot_request = request.model_copy(update={"private_input": "{}"})
    elif fault == "cancelled":
        from types import SimpleNamespace

        def cancelled() -> None:
            raise OSError("original operation cancelled")

        with pytest.raises(OSError):
            a.verify_task(
                p.spec.configuration, request, SimpleNamespace(checkpoint=cancelled)
            )
        assert calls == []
        return
    if fault == "normal":
        for _ in range(2):
            with pytest.raises(PhysicalGateReached):
                a.verify_task(p.spec.configuration, request, control)
        assert calls == [(None, None), (None, None)]
        assert sum(ref in private_refs for ref in body_reads) == 2 * len(private_refs)
    else:
        with pytest.raises(OwnershipConflict):
            a.verify_task(p.spec.configuration, request, control)
        assert calls == []
    assert p.state.snapshot_request is not None
    assert p.state.snapshot_result is p.state.snapshot_ref is None


@pytest.mark.parametrize(
    "fault", ["normal", "intent_producer", "intent_changed", "cancelled"]
)
def test_actual_admin_pending_snapshot_to_strict_native_codec(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    fault: str,
) -> None:
    c = owned_navigation_case(tmp_path, node_path, monkeypatch, contracts)
    check_original_pending_snapshot(c.owned.bundle, monkeypatch, fault)
    assert c.owned.resources.site.phase == "new" and c.owned.resources.browser() is None


@pytest.mark.parametrize(
    "fault", ["normal", "intent_producer", "intent_changed", "cancelled"]
)
def test_actual_all4_group_pending_snapshot_to_strict_native_codec(
    group_owned: Any, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    check_original_pending_snapshot(group_owned.owned.bundle, monkeypatch, fault)
    assert (
        group_owned.owned.resources.site.phase == "new"
        and group_owned.owned.resources.browser() is None
    )


@pytest.mark.parametrize(
    "fault", ["normal", "intent_producer", "intent_changed", "cancelled"]
)
def test_actual_map_pending_snapshot_keeps_original_codec(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as x:
        check_original_pending_snapshot(x.bundle, monkeypatch, fault)
        assert x.p.requests == [] and x.native.loader.session.calls == 0

"""Original registered authority binding; no native fallback or new ledger."""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.task_site_authority import TaskSiteAuthority
from lab_generate_skill.adapters.sites.resource import registered_site
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.ports.lifecycle import OperationControl
from site_resource_fixtures import resource_case
from test_slurm_commands import guard
from test_site_resource import inspect


class Native:
    def __init__(self) -> None:
        self.calls = 0

    def verify_task(
        self,
        configuration: SiteWorkerConfiguration,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls += 1


@pytest.mark.parametrize(
    "mode", ["normal", "unbound", "rebind", "wrong-start", "wrong-thread", "bad-type"]
)
def test_registered_original_native_supplier_is_bound_once_and_has_no_resource_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    c = resource_case(tmp_path, monkeypatch)

    def legacy(*args: Any, **kwargs: Any) -> None:
        pytest.fail("legacy task permission must not be used")

    monkeypatch.setattr(c.authority, "verify_task", legacy)
    a, n = TaskSiteAuthority(c.spec, c.op, c.authority, origin=None), Native()
    request = SiteTaskRequest(
        task=TaskIdentity(
            source_task_id="unit",
            task_id="unit",
            site=c.spec.configuration.site_id,
            split="train",
            family="unit",
            contract_version=1,
        ),
        binding_ref=c.spec.token.recovery_ref.model_copy(
            update={"content_schema": "task-binding/1"}
        ),
        operation=c.op.model_copy(
            update={"attempt_id": "attempt", "operation_id": "native-snapshot"}
        ),
        action="snapshot",
        private_input="{}",
    )
    with registered_site(
        c.spec,
        c.op,
        journal=c.journal,
        evidence=c.evidence,
        controls=c.controls,
        clock=c.clock,
        authority=a,
    ) as live:
        if mode == "unbound":
            with pytest.raises(OwnershipConflict, match="not active"):
                a.verify_task(c.spec.configuration, None, guard())  # type: ignore[arg-type]
        elif mode == "wrong-start":
            wrong = live.site.model_copy(
                update={
                    "instance": live.site.instance.model_copy(
                        update={
                            "endpoint": "http://127.0.0.1:39999/",
                            "ports": (39999,),
                        }
                    )
                }
            )
            with pytest.raises(OwnershipConflict, match="replaced"):
                a.bind_native(n, wrong)
        elif mode == "wrong-thread":
            with ThreadPoolExecutor(max_workers=1) as pool:
                with pytest.raises(OwnershipConflict, match="owner"):
                    pool.submit(a.bind_native, n, live.site).result()
        elif mode == "bad-type":
            with pytest.raises(OwnershipConflict, match="supplier required"):
                a.bind_native({}, live.site)  # type: ignore[arg-type]
        else:
            a.bind_native(n, live.site)
            if mode == "rebind":
                with pytest.raises(OwnershipConflict, match="one-shot"):
                    a.bind_native(n, live.site)
            a.verify_task(c.spec.configuration, request, guard())
            assert n.calls == 1
    assert inspect(c).state == "closed" and c.authority.close_calls == 1
    with pytest.raises(OwnershipConflict):
        a.bind_native(n, live.site)


def test_no_resource_policy_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = resource_case(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="mandatory"):
        TaskSiteAuthority(c.spec, c.op, None, origin=None)  # type: ignore[arg-type]


@pytest.mark.parametrize("phase", ["spawn", "ready", "started", "closed"])
def test_binding_never_overrides_original_resource_source_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    c = resource_case(tmp_path, monkeypatch)
    c.authority.deny = phase
    a = TaskSiteAuthority(c.spec, c.op, c.authority, origin=None)
    with pytest.raises((PermissionError, BaseExceptionGroup)):
        with registered_site(
            c.spec,
            c.op,
            journal=c.journal,
            evidence=c.evidence,
            controls=c.controls,
            clock=c.clock,
            authority=a,
        ):
            if phase != "closed":
                pytest.fail("Original source denied resource use")
    if phase == "spawn":
        assert not c.channels
    else:
        assert c.channels[0].capture.termination is not None
        assert inspect(c).state == ("quarantined" if phase == "closed" else "closed")

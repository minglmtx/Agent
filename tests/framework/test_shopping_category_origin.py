"""Version9 category origin/pins and the actual existing exclusive port lease."""

import hashlib
import builtins
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.network.loopback_ports import (
    LoopbackPorts,
    PortsUnavailable,
)
from lab_generate_skill.adapters.network import port_files
from lab_generate_skill.bootstrap.site_instance import build_site_instance
from lab_generate_skill.bootstrap.shopping_category_source_records import (
    CategoryNavigationSourceRecordPolicy,
)
from lab_generate_skill.domain.shopping_navigation_origin import (
    ShoppingCategoryOrigin,
    ShoppingCategoryWorkerInputs,
)
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.sites.shopping.tasks.navigation_native_request import (
    CategoryNavigationNativeRequestChecks,
)
from shopping_category_request_fixtures import request_case, saved, NativeRequestCase
from site_instance_fixtures import node_path as node_path
from site_worker_fixtures import configuration
from test_shopping_category_navigation_input import originals as originals, reference
from test_slurm_commands import guard


def selected(c: NativeRequestCase) -> SiteWorkerConfiguration:
    attempt = c.first.operation.attempt_id
    assert attempt is not None
    private = c.first.private_input
    from lab_generate_skill.sites.shopping.tasks.navigation_state import (
        CategoryNavigationExecutionInput,
    )

    data = CategoryNavigationExecutionInput.model_validate_json(private)
    return SiteWorkerConfiguration.model_validate(
        c.configuration.model_copy(
            update={
                "schema_version": "site-worker-configuration/9",
                "shopping_category_inputs": ShoppingCategoryWorkerInputs(
                    scope=StateScope(
                        owner=c.configuration.token.owner,
                        task=c.first.task,
                        attempt_id=attempt,
                        context_id="original-category",
                    ),
                    native_contract_sha256=data.spec.native_contract_ref.sha256,
                    private_input_sha256=hashlib.sha256(private.encode()).hexdigest(),
                    origin=ShoppingCategoryOrigin(endpoint="http://127.0.0.1:12001/"),
                ),
            }
        )
    )


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        123,
        {},
        "",
        "https://127.0.0.1:12001/",
        "http://localhost:12001/",
        "http://127.0.0.1:12001",
        "http://127.0.0.1:12001/admin",
        "http://127.0.0.1:12001/?x=1",
        "http://127.0.0.1:12001/#x",
        "http://user@127.0.0.1:12001/",
        "http://127.0.0.1:80/",
        "http://127.0.0.1:012001/",
    ],
)
def test_origin_refuses_missing_untyped_or_changed_root(value: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        ShoppingCategoryOrigin(endpoint=value)


def test_selected_factory_uses_exact_exclusive_web_port_and_releases_original_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, originals: Any
) -> None:
    monkeypatch.setattr(port_files, "namespace", lambda: tmp_path / "port-locks")
    original = LoopbackPorts().reserve(1, guard())
    port = original.ports[0]
    original.release(guard())
    origin = ShoppingCategoryOrigin(endpoint=f"http://127.0.0.1:{port}/")
    assert origin.web_port == port
    cfg = configuration()
    raw, _, public = originals[0]
    policy = CategoryNavigationSourceRecordPolicy(raw, reference(raw), public)
    from lab_generate_skill.sites.shopping.tasks.navigation_state import (
        CategoryNavigationExecutionInput,
    )
    from lab_generate_skill.sites.shopping.worker_instance import ShoppingWorkerInstance

    cfg = SiteWorkerConfiguration.model_validate(
        cfg.model_copy(
            update={
                "site_id": "shopping",
                "schema_version": "site-worker-configuration/9",
                "shopping_category_inputs": ShoppingCategoryWorkerInputs(
                    scope=StateScope(
                        owner=cfg.token.owner,
                        task=public.identity,
                        attempt_id="original",
                        context_id="original",
                    ),
                    native_contract_sha256=reference(raw).sha256,
                    private_input_sha256=hashlib.sha256(
                        CategoryNavigationExecutionInput(spec=policy.private)
                        .model_dump_json()
                        .encode()
                    ).hexdigest(),
                    origin=origin,
                ),
            }
        )
    )
    original_import = builtins.__import__

    def no_customer(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "lab_generate_skill.adapters.browsergym.login_catalog":
            raise AssertionError("Category factory must not import ETA login resources")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_customer)
    worker = build_site_instance(cfg)
    assert isinstance(worker, ShoppingWorkerInstance) and worker.instance.state == "new"
    with pytest.raises(ValueError, match="cannot acquire ETA"):
        worker.customer(guard())
    site = worker.instance
    lease = site.ports.reserve(5, guard())
    try:
        assert lease.ports[0] == port
        with pytest.raises(PortsUnavailable):
            second_worker = build_site_instance(cfg)
            assert isinstance(second_worker, ShoppingWorkerInstance)
            second_worker.instance.ports.reserve(5, guard())
    finally:
        lease.release(guard())
    final_worker = build_site_instance(cfg)
    assert isinstance(final_worker, ShoppingWorkerInstance)
    second = final_worker.instance.ports.reserve(5, guard())
    assert second.ports[0] == port
    second.release(guard())


def test_all18_version9_native_bindings_keep_original_contract_input_and_snapshot(
    node_path: Path, originals: Any
) -> None:
    checker = CategoryNavigationNativeRequestChecks()
    for raw, _, public in originals:
        c = request_case(node_path / public.identity.source_task_id, raw, public)
        try:
            cfg = selected(c)
            count = len(c.commands.calls)
            checker.verify_inputs(
                cfg, c.first, c.binding, c.recovery, c.environment, None, None, guard()
            )
            assert len(c.commands.calls) == count
            prepare, body = saved(c)
            count = len(c.commands.calls)
            checker.verify_inputs(
                cfg,
                prepare,
                c.binding,
                c.recovery,
                c.environment,
                body,
                c.first,
                guard(),
            )
            assert len(c.commands.calls) == count
            assert cfg.shopping_category_inputs is not None
            assert cfg.shopping_category_inputs.scope.task == public.identity
        finally:
            c.worker.stop(guard())


@pytest.mark.parametrize(
    "fault",
    [
        "native",
        "private",
        "task",
        "attempt",
        "origin",
        "owner",
        "legacy",
        "missing",
        "site",
    ],
)
def test_mismatched_new_input_scope_origin_or_version_refused_before_native_effects(
    node_path: Path, originals: Any, fault: str
) -> None:
    raw, _, public = originals[0]
    c = request_case(node_path, raw, public)
    try:
        cfg = selected(c)
        inputs = cfg.shopping_category_inputs
        assert inputs is not None
        prepare, body = saved(c)
        if fault in {"native", "private"}:
            key = (
                "native_contract_sha256"
                if fault == "native"
                else "private_input_sha256"
            )
            inputs = inputs.model_copy(update={key: "0" * 64})
        elif fault in {"task", "attempt", "owner"}:
            scope = inputs.scope
            if fault == "task":
                scope = scope.model_copy(update={"task": originals[1][2].identity})
            elif fault == "attempt":
                scope = scope.model_copy(update={"attempt_id": "foreign"})
            else:
                scope = scope.model_copy(
                    update={
                        "owner": scope.owner.model_copy(update={"owner_id": "foreign"})
                    }
                )
            inputs = inputs.model_copy(update={"scope": scope})
        elif fault == "origin":
            inputs = inputs.model_copy(
                update={
                    "origin": ShoppingCategoryOrigin(endpoint="http://127.0.0.1:12009/")
                }
            )
        changes: dict[str, Any] = {"shopping_category_inputs": inputs}
        if fault == "legacy":
            changes["schema_version"] = "site-worker-configuration/6"
        elif fault == "missing":
            changes["shopping_category_inputs"] = None
        elif fault == "site":
            changes["site_id"] = "shopping_admin"
        cfg = cfg.model_copy(update=changes)
        count = len(c.commands.calls)
        expected = (
            ValueError
            if fault in {"owner", "legacy", "missing", "site"}
            else OwnershipConflict
        )
        with pytest.raises(expected):
            CategoryNavigationNativeRequestChecks().verify_inputs(
                cfg,
                prepare,
                c.binding,
                c.recovery,
                c.environment,
                body,
                c.first,
                guard(),
            )
        assert len(c.commands.calls) == count
    finally:
        c.worker.stop(guard())


def test_old_explicit_configuration_wire_does_not_gain_category_inputs() -> None:
    legacy = configuration()
    raw = legacy.model_dump_json()
    assert '"shopping_category_inputs"' not in raw
    assert SiteWorkerConfiguration.model_validate_json(raw).model_dump_json() == raw

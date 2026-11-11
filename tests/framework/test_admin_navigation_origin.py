"""Explicit origin, actual cooperative port conflicts and legacy wire retention.

Native services remain explicit fixtures. Actual leases do not prove website
shutdown; the original outer resource still owns physical closure.
"""

import hashlib
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.admin_navigation_origin import (
    AdminNavigationOrigin,
    AdminNavigationWorkerInputs,
)
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.adapters.network.loopback_ports import (
    LoopbackPorts,
    PortsUnavailable,
)
from lab_generate_skill.bootstrap.site_instance import build_site_instance
from lab_generate_skill.sites.shopping_admin.tasks.navigation_input import (
    bind_admin_navigation,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationExecutionInput,
)
from lab_generate_skill.sites.shopping_admin.worker_instance import AdminWorkerInstance
from test_admin_navigation_input import contracts as contracts
from site_worker_fixtures import configuration
from test_admin_instance import instance
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_all71_explicit_inputs_reach_same_native_factory_without_acquisition(
    contracts: Any,
) -> None:
    base = configuration()
    for native, ref, public in contracts:
        private = NavigationExecutionInput(
            spec=bind_admin_navigation(native, ref, public).private_spec
        )
        inputs = AdminNavigationWorkerInputs(
            scope=StateScope(
                owner=base.token.owner,
                task=public.identity,
                attempt_id="attempt",
                context_id="context",
            ),
            native_contract_sha256=ref.sha256,
            private_input_sha256=hashlib.sha256(
                private.model_dump_json().encode()
            ).hexdigest(),
            origin=AdminNavigationOrigin(endpoint="http://127.0.0.1:18080/admin"),
        )
        config = SiteWorkerConfiguration.model_validate(
            base.model_copy(
                update={
                    "schema_version": "site-worker-configuration/7",
                    "admin_navigation_inputs": inputs,
                }
            )
        )
        assert (
            SiteWorkerConfiguration.model_validate_json(config.model_dump_json())
            == config
        )
        worker = build_site_instance(config)
        assert isinstance(worker, AdminWorkerInstance)
        assert worker.instance.plan.navigation_origin == inputs.origin
        assert worker.instance.port_lease is None and worker.instance.state == "new"


def test_original_actual_version6_resource_bytes_are_unchanged() -> None:
    sha = "10338582e5c6b0b99eec5d7020ac0362f5e5f2c91388303ee3886582cfbb403f"
    blob = (
        Path(
            "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-navigation42-production-20261102-v1/production-4894088/evidence/blobs"
        )
        / sha
    )
    raw = blob.read_bytes()
    assert len(raw) == 382344 and hashlib.sha256(raw).hexdigest() == sha
    spec = SiteResourceSpec.model_validate_json(raw)
    assert spec.configuration.schema_version == "site-worker-configuration/6"
    assert spec.configuration.admin_navigation_inputs is None
    assert spec.model_dump_json().encode() == raw
    base = configuration()
    assert "admin_navigation_inputs" not in base.model_dump()


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "https://127.0.0.1:18080/admin",
        "http://localhost:18080/admin",
        "http://127.0.0.1:80/admin",
        "http://127.0.0.1:18080/admin/",
        "http://127.0.0.1:18080/admin?x=1",
        "http://user@127.0.0.1:18080/admin",
        True,
        None,
    ],
)
def test_invalid_origin_has_no_resource_effects(endpoint: Any) -> None:
    with pytest.raises(ValidationError):
        AdminNavigationOrigin(endpoint=endpoint)


def test_missing_version7_inputs_and_wrong_version_are_refused(contracts: Any) -> None:
    base = configuration()
    with pytest.raises(ValueError):
        SiteWorkerConfiguration.model_validate(
            base.model_copy(update={"schema_version": "site-worker-configuration/7"})
        )
    task = contracts[0][2].identity
    inputs = AdminNavigationWorkerInputs(
        scope=StateScope(
            owner=base.token.owner,
            task=task,
            attempt_id="attempt",
            context_id="context",
        ),
        native_contract_sha256="a" * 64,
        private_input_sha256="b" * 64,
        origin=AdminNavigationOrigin(endpoint="http://127.0.0.1:18080/admin"),
    )
    for changed in (
        base.model_copy(update={"admin_navigation_inputs": inputs}),
        base.model_copy(
            update={
                "schema_version": "site-worker-configuration/7",
                "site_id": "shopping",
                "admin_navigation_inputs": inputs,
            }
        ),
        base.model_copy(
            update={
                "schema_version": "site-worker-configuration/7",
                "admin_navigation_inputs": inputs.model_copy(
                    update={
                        "scope": inputs.scope.model_copy(
                            update={
                                "owner": inputs.scope.owner.model_copy(
                                    update={"job_id": "other"}
                                )
                            }
                        )
                    }
                ),
            }
        ),
    ):
        with pytest.raises(ValueError):
            SiteWorkerConfiguration.model_validate(changed)


@pytest.mark.parametrize("fault", ["none", "ports", "files", "wrong_port", "cancel"])
def test_exact_origin_reservation_precedes_staging_and_retains_partial_lease(
    node_path: Path, fault: str
) -> None:
    site, allocator, _, events = instance(
        node_path, fault if fault in ("ports", "files") else None
    )
    site.plan = site.plan.model_copy(
        update={
            "navigation_origin": AdminNavigationOrigin(
                endpoint=f"http://127.0.0.1:{12006 if fault == 'wrong_port' else 12001}/admin"
            )
        }
    )
    if fault == "none":
        site.prepare(guard())
        assert site.plan.navigation_origin is not None
        assert (
            events[:2] == ["ports", "files"]
            and site.spec is not None
            and site.spec.admin_url == site.plan.navigation_origin.endpoint
        )
        count = len(events)
        with pytest.raises(RuntimeError):
            site.prepare(guard())
        assert len(events) == count
    else:
        with pytest.raises((OSError, ValueError, OperationStopped)):
            site.prepare(guard(0) if fault == "cancel" else guard())
        assert events == (
            []
            if fault == "cancel"
            else ["ports", "files"] if fault == "files" else ["ports"]
        )
        if fault in ("files", "wrong_port"):
            assert site.port_lease is allocator.lease and not allocator.lease.released


def test_actual_occupied_original_port_never_falls_back_or_stages_assets(
    node_path: Path,
) -> None:
    original = LoopbackPorts().reserve(1, guard())
    try:
        port = original.ports[0]
        site, _, _, events = instance(node_path)
        site.plan = site.plan.model_copy(
            update={
                "navigation_origin": AdminNavigationOrigin(
                    endpoint=f"http://127.0.0.1:{port}/admin"
                )
            }
        )
        site._ports = LoopbackPorts(required_prefix=(port,))
        with pytest.raises(PortsUnavailable):
            site.prepare(guard())
        assert not events and site.port_lease is None
        with pytest.raises(PortsUnavailable):
            LoopbackPorts(required_prefix=(port,)).reserve(1, guard())
    finally:
        original.release(guard())
    fresh = LoopbackPorts(required_prefix=(port,)).reserve(1, guard())
    assert fresh.ports == (port,)
    fresh.release(guard())

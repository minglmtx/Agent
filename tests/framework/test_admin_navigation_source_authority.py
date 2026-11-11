"""Actual Slurm source caller, synthetic asset declarations, no site/model launch."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
import hashlib
import pytest
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_current_cgroup
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.adapters.sites.admin_navigation_source_authority import (
    AdminNavigationSourceSiteAuthority,
)
from lab_generate_skill.adapters.sites.source_qualification_authority import (
    SourceQualificationSiteAuthority,
)
from lab_generate_skill.domain.admin_navigation_origin import (
    AdminNavigationOrigin,
    AdminNavigationWorkerInputs,
)
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.site_resource import (
    SiteResourceSpec,
    SiteResourceAttempt,
)
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.sites.shopping_admin.tasks.navigation_input import (
    bind_admin_navigation,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationExecutionInput,
)
from site_worker_fixtures import configuration
from site_resource_fixtures import resource_case, Case
from site_instance_fixtures import node_path as node_path
from test_admin_navigation_input import contracts as contracts
from test_linux_cgroups import actual_slurm_execution
from test_slurm_commands import guard


def source_case(
    root: Path, node: Path, patch: pytest.MonkeyPatch, contracts: Any
) -> tuple[OriginalSourceQualificationOwner, Case]:
    execution, _ = actual_slurm_execution()
    controller = observe_current_cgroup(
        execution, current_process_identity(), guard(30)
    ).membership
    native, ref, public = contracts[0]
    private = bind_admin_navigation(native, ref, public).private_spec
    cfg = configuration(job_id=execution.job_id)
    scope = StateScope(
        owner=cfg.token.owner,
        task=public.identity,
        attempt_id="source-only-admin",
        context_id="source-context",
    )
    cfg = SiteWorkerConfiguration.model_validate(
        cfg.model_copy(
            update={
                "schema_version": "site-worker-configuration/7",
                "files": cfg.files.model_copy(
                    update={"node_root": str(node / "fresh-source")}
                ),
                "admin_navigation_inputs": AdminNavigationWorkerInputs(
                    scope=scope,
                    native_contract_sha256=ref.sha256,
                    private_input_sha256=hashlib.sha256(
                        NavigationExecutionInput(spec=private)
                        .model_dump_json()
                        .encode()
                    ).hexdigest(),
                    origin=AdminNavigationOrigin(
                        endpoint="http://127.0.0.1:12001/admin"
                    ),
                ),
            }
        )
    )
    c = resource_case(root, patch, config=cfg)
    c.spec = SiteResourceSpec.model_validate(
        c.spec.model_copy(
            update={
                "slurm": c.spec.slurm.model_copy(
                    update={"execution": execution, "parent": controller}
                )
            }
        )
    )
    owner = OriginalSourceQualificationOwner(scope, execution, controller, c.evidence)
    return owner, c


def test_actual_admin_source_caller_one_spawn_configure_and_unconfirmed_close(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> None:
    owner, c = source_case(tmp_path, node_path, monkeypatch, contracts)
    auth = AdminNavigationSourceSiteAuthority(owner, c.spec, c.op)
    control = c.controls.bind(c.op)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(OwnershipConflict):
            pool.submit(auth.authorize_spawn, c.spec, c.op, control).result()
    assert not auth._spawn
    auth.authorize_spawn(c.spec, c.op, control)
    with pytest.raises(OwnershipConflict):
        auth.authorize_spawn(c.spec, c.op, control)
    auth.verify(c.spec.configuration, "configure", c.op, control)
    with pytest.raises(OwnershipConflict):
        auth.verify(c.spec.configuration, "configure", c.op, control)
    with pytest.raises(OwnershipConflict):
        auth.verify(c.spec.configuration, "start", c.op, control)
    with pytest.raises(OwnershipConflict, match="supplier"):
        from admin_navigation_fixtures import request

        auth.verify_task(c.spec.configuration, request(contracts), control)
    close = c.op.cleanup("source-close", now=c.op.deadline, seconds=30)
    with pytest.raises(OwnershipConflict, match="unconfirmed"):
        auth.verify_closed(
            c.spec,
            SiteResourceAttempt(spawn_attempted=False),
            None,
            None,
            close,
            c.controls.bind(close),
        )
    assert c.channels == []


@pytest.mark.parametrize("fault", ["map-only", "scope", "missing"])
def test_wrong_site_scope_or_missing_version7_input_cannot_grant_source_rights(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    fault: str,
) -> None:
    owner, c = source_case(tmp_path, node_path, monkeypatch, contracts)
    if fault == "map-only":
        with pytest.raises(OwnershipConflict):
            SourceQualificationSiteAuthority(owner, c.spec, c.op)
    else:
        inputs = c.spec.configuration.admin_navigation_inputs
        assert inputs is not None
        changed = (
            None
            if fault == "missing"
            else inputs.model_copy(
                update={
                    "scope": inputs.scope.model_copy(
                        update={"context_id": "foreign-source-context"}
                    )
                }
            )
        )
        with pytest.raises((OwnershipConflict, ValueError)):
            cfg = SiteWorkerConfiguration.model_validate(
                c.spec.configuration.model_copy(
                    update={"admin_navigation_inputs": changed}
                )
            )
            spec = SiteResourceSpec.model_validate(
                c.spec.model_copy(update={"configuration": cfg})
            )
            AdminNavigationSourceSiteAuthority(owner, spec, c.op)
    assert c.channels == []


@pytest.mark.parametrize("fault", ["sealed", "used-root"])
def test_closed_owner_or_used_node_root_never_starts_new_source(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    fault: str,
) -> None:
    owner, c = source_case(tmp_path, node_path, monkeypatch, contracts)
    auth = AdminNavigationSourceSiteAuthority(owner, c.spec, c.op)
    if fault == "sealed":
        owner.seal(c.op, c.controls.bind(c.op))
    else:
        Path(c.spec.configuration.files.node_root).mkdir()
    with pytest.raises(OwnershipConflict):
        auth.authorize_spawn(c.spec, c.op, c.controls.bind(c.op))
    assert c.channels == []

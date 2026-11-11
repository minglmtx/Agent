"""Whole Group declarations, real held ports, and pre-effect identity refusals."""

import hashlib
from pathlib import Path
from typing import Any, cast
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.gitlab_group_origin import (
    GitlabGroupOrigin,
    GitlabGroupWorkerInputs,
)
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.ports.site_storage import SiteWorkerGuard
from lab_generate_skill.bootstrap.gitlab_instance import build_gitlab_worker
from lab_generate_skill.bootstrap.gitlab_group import load_group_inputs
from lab_generate_skill.adapters.network.loopback_ports import PortsUnavailable
from lab_generate_skill.sites.gitlab.tasks.group_worker_inputs import (
    verify_group_worker_inputs,
)
from gitlab_site_storage_live import missing_asset_configuration
from storage_installation_fixtures import storage_installation
from test_gitlab_group_complete_starts import PINS, original, ORIGIN
from gitlab_group_fixtures import reference
from site_worker_fixtures import operation
from test_slurm_commands import guard


def selected(
    root: Path, source: str
) -> tuple[SiteWorkerConfiguration, SiteTaskRequest]:
    base = missing_asset_configuration(
        storage_installation(),
        job_id="4752096",
        root=root,
        parent=Path("/tmp/group-origin-unit"),
    )
    assert base.private_evidence is not None
    raw, _, public = original(source)
    private = load_group_inputs(raw, reference(raw), public)
    inputs = GitlabGroupWorkerInputs(
        scope=StateScope(
            owner=base.token.owner,
            task=public.identity,
            attempt_id="attempt",
            context_id="context",
        ),
        native_contract_sha256=private.native_contract_ref.sha256,
        private_input_sha256=hashlib.sha256(
            private.model_dump_json().encode()
        ).hexdigest(),
        origin=GitlabGroupOrigin(endpoint=ORIGIN),
    )
    config = SiteWorkerConfiguration.model_validate(
        base.model_copy(
            update={
                "schema_version": "site-worker-configuration/8",
                "gitlab_group_inputs": inputs,
                "private_evidence": base.private_evidence.model_copy(
                    update={"profile": GITLAB_GROUP_PRIVATE_JSON}
                ),
            }
        )
    )
    op = operation(config).model_copy(update={"attempt_id": "attempt"})
    request = SiteTaskRequest(
        task=public.identity,
        binding_ref=reference(raw).model_copy(
            update={"content_schema": "task-binding/1"}
        ),
        operation=op,
        action="snapshot",
        private_input=private.model_dump_json(),
    )
    return config, request


@pytest.mark.parametrize("source", tuple(PINS))
def test_all_four_original_inputs_bind_same_factory_and_retain_exact_wire(
    tmp_path: Path,
    source: str,
) -> None:
    config, request = selected(tmp_path, source)
    assert (
        SiteWorkerConfiguration.model_validate_json(config.model_dump_json()) == config
    )
    worker = build_gitlab_worker(config, cast(SiteWorkerGuard, None))
    assert worker.instance.state == "new" and worker.instance.lease is None
    assert not Path(config.files.node_root).exists()
    verify_group_worker_inputs(config, request)
    verify_group_worker_inputs(config, request)
    # The real original allocator must hold the declared first port; no fallback.
    first = worker.instance.ports.reserve(2, guard())
    try:
        assert first.ports[0] == 18080 and len(set(first.ports)) == 2
        with pytest.raises(PortsUnavailable):
            worker.instance.ports.reserve(2, guard())
    finally:
        first.release(guard())
    again = worker.instance.ports.reserve(2, guard())
    again.release(guard())


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        None,
        True,
        18080,
        "https://127.0.0.1:18080/",
        "http://localhost:18080/",
        "http://127.0.0.1:80/",
        "http://127.0.0.1:18080",
        "http://127.0.0.1:18080/?x=1",
        "http://user@127.0.0.1:18080/",
        "http://127.0.0.1:18080/groups/new",
        "http://127.0.0.1:018080/",
    ],
)
def test_invalid_origin_is_refused(endpoint: Any) -> None:
    with pytest.raises(ValidationError):
        GitlabGroupOrigin(endpoint=endpoint)


@pytest.mark.parametrize(
    "fault", ["missing", "version6", "version7", "owner", "profile", "family", "split"]
)
def test_invalid_configuration_refused_before_acquisition(
    tmp_path: Path, fault: str
) -> None:
    config, _ = selected(tmp_path, next(iter(PINS)))
    assert (
        config.gitlab_group_inputs is not None and config.private_evidence is not None
    )
    data = config.model_dump(mode="json")
    if fault == "missing":
        data["gitlab_group_inputs"] = None
    elif fault.startswith("version"):
        data["schema_version"] = "site-worker-configuration/" + fault[-1]
    elif fault == "owner":
        data["gitlab_group_inputs"]["scope"]["owner"]["owner_id"] = "foreign"
    elif fault == "profile":
        data["private_evidence"] = None
    else:
        data["gitlab_group_inputs"]["scope"]["task"][fault] = "foreign"
    with pytest.raises(ValidationError):
        SiteWorkerConfiguration.model_validate(data)
    assert not Path(config.files.node_root).exists()


@pytest.mark.parametrize("fault", ["task", "attempt", "private", "native"])
def test_changed_original_request_refused_without_native_call(
    tmp_path: Path, fault: str
) -> None:
    config, request = selected(tmp_path, next(iter(PINS)))
    assert config.gitlab_group_inputs is not None
    declared = config.gitlab_group_inputs
    if fault == "task":
        declared = declared.model_copy(
            update={
                "scope": declared.scope.model_copy(
                    update={
                        "task": declared.scope.task.model_copy(
                            update={"source_task_id": "foreign"}
                        )
                    }
                )
            }
        )
    elif fault == "attempt":
        declared = declared.model_copy(
            update={
                "scope": declared.scope.model_copy(update={"attempt_id": "foreign"})
            }
        )
    else:
        field = (
            "private_input_sha256" if fault == "private" else "native_contract_sha256"
        )
        declared = declared.model_copy(update={field: "0" * 64})
    config = SiteWorkerConfiguration.model_validate(
        config.model_copy(update={"gitlab_group_inputs": declared})
    )
    worker = build_gitlab_worker(config, cast(SiteWorkerGuard, None))
    with pytest.raises(OwnershipConflict, match="original declared"):
        worker.execute_task(request, control=guard())
    assert worker.instance.state == "new" and not worker.instance.generations

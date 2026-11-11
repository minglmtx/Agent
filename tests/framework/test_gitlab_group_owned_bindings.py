"""All four Group branches on real source/claim codecs and explicit unit effects.

No real Group instance, model, benchmark replay or runtime qualification is
created; claims and evidence are isolated pytest data.
"""

from pathlib import Path
from typing import Any

import pytest

from lab_generate_skill.bootstrap.gitlab_group_claimed_authority import (
    GroupClaimedSiteAuthority,
)
from lab_generate_skill.bootstrap.gitlab_group_execution_admission import (
    admit_gitlab_group_execution_source,
)
from lab_generate_skill.bootstrap.gitlab_group_owned_execution import (
    gitlab_group_owned_execution,
)
from lab_generate_skill.bootstrap.gitlab_group_task_browser_declarations import (
    OriginalGroupTaskBrowserDeclarations,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from gitlab_group_owned_fixtures import owned_group_case
from test_gitlab_group_complete_starts import PINS
from test_gitlab_group_origin_composition import fixture_origin
from test_gitlab_group_source_composition import contracts_for
from site_instance_fixtures import node_path as node_path


@pytest.fixture(params=tuple(PINS))
def group_owned(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> Any:
    selected = str(request.param)
    fixture_origin(monkeypatch, selected)
    return owned_group_case(tmp_path, node_path, monkeypatch, contracts_for(selected))


def test_all_group_branches_bind_original_owner_source_and_task_without_acquisition(
    group_owned: Any,
    tmp_path: Path,
) -> None:
    c = group_owned
    owned, source = c.owned, c.source
    assert owned.bundle.preparation.declaration == c.declarations.preparation
    assert owned.bundle.task.plan.intent == c.admitted.published.source.intent
    assert owned.resources.site.phase == owned.bundle.preparation.state.phase == "new"
    assert owned.resources.browser() is None
    rights = owned.physical_site.source
    assert isinstance(rights, GroupClaimedSiteAuthority)
    assert owned.resources.site.authority.origin is rights
    guard = source.site.controls.bind(rights.acquisition)
    rights.verify_source(rights.acquisition, guard)
    rights.verify_origin(rights.spec, rights.acquisition, guard)
    assert not rights._spawn
    with pytest.raises(OwnershipConflict):
        owned.bundle.initialization.original()
    assert not (tmp_path / "candidate-trace").exists()
    assert not (tmp_path / "candidate-calls").exists()


def test_group_full_scope_native_private_and_public_origin_reject_before_spawn(
    group_owned: Any,
) -> None:
    owned = group_owned.owned
    original = owned.physical_site.source
    inputs = original.spec.configuration.gitlab_group_inputs
    assert inputs is not None
    variants = (
        inputs.model_copy(update={"native_contract_sha256": "0" * 64}),
        inputs.model_copy(update={"private_input_sha256": "0" * 64}),
        inputs.model_copy(
            update={"scope": inputs.scope.model_copy(update={"context_id": "foreign"})}
        ),
        inputs.model_copy(
            update={"scope": inputs.scope.model_copy(update={"attempt_id": "foreign"})}
        ),
        inputs.model_copy(
            update={
                "origin": inputs.origin.model_copy(
                    update={"endpoint": "http://127.0.0.1:18081/"}
                )
            }
        ),
    )
    for value in variants:
        changed = original.spec.model_copy(
            update={
                "configuration": original.spec.configuration.model_copy(
                    update={"gitlab_group_inputs": value}
                )
            }
        )
        rights = GroupClaimedSiteAuthority(
            owned.resources.owner, changed, original.acquisition
        )
        with pytest.raises(OwnershipConflict):
            rights.verify_origin(
                changed,
                original.acquisition,
                group_owned.source.site.controls.bind(original.acquisition),
            )
        assert not rights._spawn
    assert owned.resources.site.phase == "new" and owned.resources.browser() is None


def test_group_origin_rechecks_live_source_permission_each_time(
    group_owned: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rights = group_owned.owned.physical_site.source
    owner = rights.owner
    actual = owner.task_source
    calls = []

    def fresh(operation: Any, control: Any) -> Any:
        calls.append(operation)
        if len(calls) > 1:
            raise PermissionError("Unit original source permission revoked")
        return actual(operation, control)

    monkeypatch.setattr(owner, "task_source", fresh)
    control = group_owned.source.site.controls.bind(rights.acquisition)
    rights.verify_origin(rights.spec, rights.acquisition, control)
    with pytest.raises(PermissionError, match="revoked"):
        rights.verify_origin(rights.spec, rights.acquisition, control)
    assert len(calls) == 2 and not rights._spawn


def test_group_foreign_owner_controller_and_missing_profile_refuse_before_spawn(
    group_owned: Any,
) -> None:
    original = group_owned.owned.physical_site.source
    cfg = original.spec.configuration
    inputs = cfg.gitlab_group_inputs
    assert inputs is not None
    foreign = inputs.scope.owner.model_copy(update={"owner_id": "foreign"})
    variants = (
        original.spec.model_copy(
            update={
                "configuration": cfg.model_copy(
                    update={
                        "gitlab_group_inputs": inputs.model_copy(
                            update={
                                "scope": inputs.scope.model_copy(
                                    update={"owner": foreign}
                                )
                            }
                        )
                    }
                )
            }
        ),
        original.spec.model_copy(
            update={"configuration": cfg.model_copy(update={"private_evidence": None})}
        ),
        original.spec.model_copy(
            update={
                "slurm": original.spec.slurm.model_copy(
                    update={
                        "execution": original.spec.slurm.execution.model_copy(
                            update={"job_id": "999999"}
                        )
                    }
                )
            }
        ),
    )
    for spec in variants:
        with pytest.raises((ValueError, OwnershipConflict)):
            GroupClaimedSiteAuthority(original.owner, spec, original.acquisition)
    assert not original._spawn and group_owned.owned.resources.site.phase == "new"


@pytest.mark.parametrize("value", [None, "", {}, [], 0, True])
def test_group_explicit_owner_reader_and_declarations_required(value: Any) -> None:
    with pytest.raises(TypeError):
        admit_gitlab_group_execution_source(
            value,
            value,
            value,
            value,
            value,
            value,
            claim_root=value,
            claim_scope=value,
            evidence=value,
            controls=value,
            source_reads=value,
        )
    with pytest.raises(TypeError):
        gitlab_group_owned_execution(
            value,
            value,
            value,
            value,
            value,
            value,
            value,
            journal=value,
            bindings=value,
            controls=value,
            clock=value,
            trace_root=value,
            calls_root=value,
            trace_capacity=value,
        )
    with pytest.raises(TypeError):
        OriginalGroupTaskBrowserDeclarations(value, value, value, value, value)

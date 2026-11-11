"""Pinned real image declarations on explicit unit source-owner premises.

No image staging, port reservation, site/source grant, model or claim occurs.
The actual isolated installation is reused as declaration data only.
"""

from pathlib import Path
from typing import Any
import json
import pytest
from admin_production_site import declare_original_admin_site, ADMIN_IMAGE, ADMIN_SOURCE
from admin_production_inputs import load_admin_navigation_group
from production_inputs import OriginalDocuments
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from test_admin_navigation_source_authority import source_case
from test_admin_navigation_input import contracts as contracts
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.fixture
def case(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> Any:
    owner, c = source_case(tmp_path, node_path, monkeypatch, contracts)
    selected = load_admin_navigation_group(guard(60))[0]
    original = c.spec.configuration.admin_navigation_inputs
    assert original is not None
    p = Path(
        "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-admin-navigation-production-20261102-v1/check-isolated-4902561/admin-deployment.json"
    )
    installation = ReleaseInstallation.model_validate_json(
        json.dumps(json.loads(p.read_bytes())["installation"])
    )
    kwargs = dict(
        selected=selected,
        scope=owner.scope,
        installation=installation,
        slurm=c.spec.slurm,
        origin=original.origin,
        node_root=node_path / "admin-declared",
        documents=OriginalDocuments(c.evidence, c.controls),
        operation=c.op.model_copy(update={"allocation_id": None, "recovery_ref": None}),
        clock=c.clock,
        prefix="source",
        site_seconds=120,
        allowed_actions=("click", "send_msg_to_user"),
        defer_acquisition=False,
    )
    return c, kwargs


def test_original_real_image_and_full_environment_recovery_before_source(
    case: Any,
) -> None:
    c, kwargs = case
    actual = declare_original_admin_site(**kwargs)
    assert actual.spec.configuration.files.image == ADMIN_IMAGE
    assert actual.spec.configuration.files.source_path == str(ADMIN_SOURCE)
    bound = actual.spec.configuration.admin_navigation_inputs
    assert bound is not None
    assert bound.scope == kwargs["scope"]
    assert actual.spec.token.owner == kwargs["scope"].owner
    assert actual.public.identity == kwargs["selected"].private.task
    assert actual.public.goal == kwargs["selected"].goal
    recovery = RecoveryPlan.model_validate_json(
        c.evidence.read(actual.spec.token.recovery_ref)
    )
    assert recovery.restore_component_id == "admin-frontend"
    assert recovery.state_coverage == ("admin.frontend.resumed",)
    assert recovery.baseline_ref == actual.state_ref
    assert actual.acquisition.deadline <= kwargs["operation"].deadline
    assert not actual.deferred_acquisition
    assert not tuple(c.journal._root.glob("*.resource.json"))
    assert not kwargs["node_root"].exists()


@pytest.mark.parametrize(
    "fault", ["task", "owner", "budget", "origin", "node", "actions", "prefix"]
)
def test_bad_final_join_rejected_before_any_publication(
    case: Any, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c, kwargs = case

    def no_put(*args: Any, **kw: Any) -> Any:
        pytest.fail("Invalid Admin declaration reached CAS")

    monkeypatch.setattr(c.evidence, "put", no_put)
    if fault == "task":
        kwargs["scope"] = kwargs["scope"].model_copy(
            update={
                "task": kwargs["scope"].task.model_copy(
                    update={"source_task_id": "foreign", "task_id": "foreign"}
                )
            }
        )
    elif fault == "owner":
        kwargs["operation"] = kwargs["operation"].model_copy(
            update={"owner_id": "foreign"}
        )
    elif fault == "budget":
        kwargs["site_seconds"] = True
    elif fault == "origin":
        kwargs["origin"] = kwargs["origin"].model_copy(
            update={"endpoint": "http://external.invalid/admin"}
        )
    elif fault == "node":
        kwargs["node_root"] = Path("/etc/admin")
    elif fault == "actions":
        kwargs["allowed_actions"] = ()
    else:
        kwargs["prefix"] = ""
    with pytest.raises((ValueError, TypeError)):
        declare_original_admin_site(**kwargs)
    assert not tuple(c.journal._root.glob("*.resource.json"))


@pytest.mark.parametrize("lost", [1, 2, 3])
def test_partial_publication_stops_without_resource_acquisition(
    case: Any, monkeypatch: pytest.MonkeyPatch, lost: int
) -> None:
    c, kwargs = case
    original = c.evidence.put
    calls: list[EvidenceRef] = []

    def put(
        raw: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        ref = EvidenceRef.model_validate(original(raw, metadata, control))
        calls.append(ref)
        if len(calls) == lost:
            raise OSError("Original declaration ACK lost")
        return ref

    monkeypatch.setattr(c.evidence, "put", put)
    with pytest.raises(OSError, match="ACK lost"):
        declare_original_admin_site(**kwargs)
    assert len(calls) == lost
    assert not tuple(c.journal._root.glob("*.resource.json"))
    assert not kwargs["node_root"].exists()


def test_deferred_candidate_keeps_unbound_parent_ceiling_before_model_wait(
    case: Any,
) -> None:
    c, kwargs = case
    kwargs["scope"] = kwargs["scope"].model_copy(
        update={"attempt_id": "candidate", "context_id": "candidate-context"}
    )
    kwargs["prefix"] = "candidate"
    kwargs["defer_acquisition"] = True
    actual = declare_original_admin_site(**kwargs)
    assert actual.deferred_acquisition
    assert actual.acquisition.deadline == kwargs["operation"].deadline
    assert actual.spec.token.allocation_id == "candidate.site"
    bound = actual.spec.configuration.admin_navigation_inputs
    assert bound is not None and bound.scope.attempt_id == "candidate"
    assert not tuple(c.journal._root.glob("*.resource.json"))
    assert not kwargs["node_root"].exists()

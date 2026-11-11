"""Exact private source lineage, actual journal/CAS; physical/source rights unit-only."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.adapters.map_artifacts.origin_authority import (
    OriginalMapOriginAuthority,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.evidence import EvidenceRef
from map_task_execution_current_fixtures import (
    current_map_execution_case,
    CurrentMapExecutionCase,
)
from map_navigation_group_cases import SOURCES
from map_origin_fixtures import source_origin
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.fixture
def current(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[CurrentMapExecutionCase]:
    with current_map_execution_case(node_path, monkeypatch, SOURCES[0]) as value:
        yield value


def alternate_source(case: CurrentMapExecutionCase) -> EvidenceRef:
    c, j = case.p.original.resource, case.journals
    other = j.source.model_copy(
        update={
            "operation": j.source.operation.model_copy(
                update={"operation_id": "unit-other-private-context"}
            )
        }
    )
    records = EvidenceContextRecords(c.evidence, c.controls, j.context)
    ref = records.publish_context(other, other.operation)
    assert ref != j.source_ref
    qualified = records.load_context(ref, case.p.plan.read_operation)
    assert qualified.public_context_ref == j.source.public_context_ref
    assert c.evidence.read(qualified.public_context_ref, guard()) == c.evidence.read(
        j.source.public_context_ref, guard()
    )
    return ref


def test_same_public_bytes_do_not_substitute_another_valid_private_source(
    current: CurrentMapExecutionCase,
) -> None:
    spec, authority = source_origin(current)
    other = alternate_source(current)
    data = spec.model_dump()
    data["configuration"]["map_inputs"]["origin"][
        "source_context_receipt_ref"
    ] = other.model_dump()
    with pytest.raises(OwnershipConflict, match="pending construction/private context"):
        authority.verify_origin(
            SiteResourceSpec.model_validate(data),
            current.p.original.resource.op,
            guard(),
        )
    assert current.p.requests == [] and current.native.loader.session.calls == 0


def test_parent_rechecks_original_construction_permission_after_a_prior_pass(
    current: CurrentMapExecutionCase,
) -> None:
    spec, authority = source_origin(current)
    authority.verify_origin(spec, current.p.original.resource.op, guard())
    current.journals.data.authority.denied = True
    with pytest.raises(OwnershipConflict, match="claim rejected"):
        authority.verify_origin(spec, current.p.original.resource.op, guard())
    assert current.p.requests == [] and current.native.loader.session.calls == 0


@pytest.mark.parametrize("fault", ["source", "read", "attempt", "owner", "cleanup"])
def test_missing_or_wrong_source_read_scope_precedes_native_effects(
    current: CurrentMapExecutionCase, fault: str
) -> None:
    spec, authority = source_origin(current)
    if fault == "source":
        authority.source = None
    elif fault == "read":
        authority.read_operation = None
    else:
        assert authority.read_operation is not None
        changes = {
            "attempt": {"attempt_id": "foreign"},
            "owner": {"owner_id": "foreign"},
            "cleanup": {"mode": "cleanup", "parent_operation_id": "unit-parent"},
        }[fault]
        authority.read_operation = authority.read_operation.model_copy(update=changes)
    with pytest.raises(OwnershipConflict):
        authority.verify_origin(spec, current.p.original.resource.op, guard())
    assert current.p.requests == []


@pytest.mark.parametrize("bad", [None, "", [], {}, True])
def test_empty_or_wrong_source_proof_is_not_a_dispatch_claim(
    current: CurrentMapExecutionCase, bad: Any
) -> None:
    spec, authority = source_origin(current)

    class InvalidProof:
        def verify_source(self, op: Any) -> Any:
            return bad

    authority.source = InvalidProof()
    with pytest.raises(ValueError):
        authority.verify_origin(spec, current.p.original.resource.op, guard())
    assert current.p.requests == [] and current.native.loader.session.calls == 0


@pytest.mark.parametrize("bad", ["", [], {}, True, 0])
def test_invalid_source_port_has_no_implicit_read_or_permission(bad: Any) -> None:
    with pytest.raises(ValueError, match="source proof required"):
        OriginalMapOriginAuthority(
            contexts=None, evidence=None, source=bad, read_operation=None
        )

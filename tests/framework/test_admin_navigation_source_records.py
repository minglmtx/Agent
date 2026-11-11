"""All71 original parameter bindings; synthetic site metadata grants no source run."""

from pathlib import Path
from typing import Any
import hashlib
import json
import pytest
from lab_generate_skill.bootstrap.admin_navigation_source_records import (
    AdminNavigationSourceRecordPolicy,
)
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.domain.admin_navigation_origin import (
    AdminNavigationWorkerInputs,
)
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceNotFound,
    EvidenceIntegrityError,
)
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationExecutionInput,
)
from site_worker_fixtures import Instance
from test_admin_navigation_input import contracts as contracts, SCOPE, GROUP
from site_instance_fixtures import node_path as node_path
from test_admin_navigation_source_authority import source_case
from test_slurm_commands import guard


def original_bytes() -> dict[str, bytes]:
    # Consume the existing selected-group pins, not guessed physical filenames.
    selected = (
        row
        for row in map(json.loads, (SCOPE / "tasks.jsonl").read_text().splitlines())
        if row["effective_batch_id"] == GROUP
    )
    return {
        row["contract_pin_check"]["expected_sha256"]: Path(
            row["contract_pin_check"]["path"]
        ).read_bytes()
        for row in selected
    }


def retain(store: Any, raw: bytes, ref: EvidenceRef) -> None:
    meta = EvidenceMetadata.model_validate(
        ref.model_dump(
            include={"media_type", "content_schema", "visibility", "producer"}
        )
    )
    assert store.put(raw, meta) == ref


def test_all71_bind_original_native_bytes_and_exact_acquired_origin_without_promotion(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> None:
    owner, c = source_case(tmp_path, node_path, monkeypatch, contracts)
    raw_by_sha = original_bytes()
    view = Instance(c.spec.configuration).start(guard(30))
    seen = set()
    for native, ref, public in contracts:
        raw = raw_by_sha[ref.sha256]
        retain(c.evidence, raw, ref)
        policy = AdminNavigationSourceRecordPolicy(raw, ref, public)
        scope = owner.scope.model_copy(update={"task": public.identity})
        current = OriginalSourceQualificationOwner(
            scope, owner.execution, owner.controller, owner.evidence
        )
        cfg = c.spec.configuration
        inputs = cfg.admin_navigation_inputs
        assert inputs is not None
        cfg = SiteWorkerConfiguration.model_validate(
            cfg.model_copy(
                update={
                    "admin_navigation_inputs": inputs.model_copy(
                        update={
                            "scope": scope,
                            "native_contract_sha256": ref.sha256,
                            "private_input_sha256": hashlib.sha256(
                                NavigationExecutionInput(spec=policy.private)
                                .model_dump_json()
                                .encode()
                            ).hexdigest(),
                        }
                    )
                }
            )
        )
        definition = policy.definition(current, cfg, view, guard(30))
        assert definition.public.identity == definition.spec.task == public.identity
        assert definition.public.goal == native["goal"]
        assert definition.public.start_url == view.endpoint + native["start_path"]
        assert (
            definition.private == policy.private
            and policy.private.admission == "unverified"
        )
        assert (
            NavigationExecutionInput.model_validate_json(definition.private_input).spec
            == policy.private
        )
        seen.add(public.identity.source_task_id)
    assert len(seen) == 71 and c.channels == []


@pytest.mark.parametrize(
    "fault", ["input", "scope", "origin", "missing-bytes", "bad-bytes"]
)
def test_source_definition_refuses_changed_scope_hash_origin_or_original_bytes(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    fault: str,
) -> None:
    owner, c = source_case(tmp_path, node_path, monkeypatch, contracts)
    _, ref, public = contracts[0]
    raw = original_bytes()[ref.sha256]
    policy = AdminNavigationSourceRecordPolicy(raw, ref, public)
    if fault != "missing-bytes":
        retain(c.evidence, raw, ref)
    cfg = c.spec.configuration
    view = Instance(cfg).start(guard(30))
    inputs = cfg.admin_navigation_inputs
    assert inputs is not None
    if fault == "input":
        cfg = cfg.model_copy(
            update={
                "admin_navigation_inputs": inputs.model_copy(
                    update={"private_input_sha256": "0" * 64}
                )
            }
        )
    elif fault == "scope":
        cfg = cfg.model_copy(
            update={
                "admin_navigation_inputs": inputs.model_copy(
                    update={
                        "scope": inputs.scope.model_copy(
                            update={"context_id": "foreign"}
                        )
                    }
                )
            }
        )
    elif fault == "origin":
        view = view.model_copy(update={"endpoint": "http://127.0.0.1:12009/admin"})
    elif fault == "bad-bytes":
        # Original evidence reader must reject a changed digest, without replacing
        # the retained immutable source. This corrupts only a fresh unit CAS.
        (tmp_path / "evidence/blobs" / ref.sha256).write_bytes(raw + b" ")
    expected: type[Exception] = (
        EvidenceNotFound
        if fault == "missing-bytes"
        else (EvidenceIntegrityError if fault == "bad-bytes" else OwnershipConflict)
    )
    with pytest.raises(expected):
        policy.definition(owner, cfg, view, guard(30))
    assert c.channels == []


def test_source_snapshot_keeps_original_request_and_rejects_retargeting(
    tmp_path: Path, contracts: Any
) -> None:
    from admin_navigation_fixtures import case, request

    _, ref, public = contracts[0]
    policy = AdminNavigationSourceRecordPolicy(
        original_bytes()[ref.sha256], ref, public
    )
    native, _ = case(tmp_path)
    original = request(contracts)
    result = native.execute_task(original, control=guard(30))
    schema, raw = policy.snapshot_bytes(original, result)
    assert (
        schema == "admin-navigation-recovery/1"
        and raw == result.private_result.encode()
    )
    changed = original.model_copy(
        update={
            "operation": original.operation.model_copy(
                update={"operation_id": "foreign"}
            )
        }
    )
    with pytest.raises(OwnershipConflict):
        policy.snapshot_bytes(changed, result)

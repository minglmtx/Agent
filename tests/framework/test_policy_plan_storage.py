"""Real CAS consumers preserve choices and refuse missing selected inputs.

Validation documents here are explicitly synthetic, not approval to enable a
real optimization. Resource/role assembly remains a separate integration gate.
"""

from lab_generate_skill.ports.lifecycle import OperationControl

from pathlib import Path

import pytest

from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.errors import EvidenceNotFound
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.optional_policies import EnabledPolicy, RunPolicies
from lab_generate_skill.domain.run_plan import RunPlan
from test_evidence_run_plans import persisted_plan, frozen_binding, loader
from test_run_journal import command


def selected_plan(store: FileEvidenceStore) -> RunPlan:
    value = persisted_plan(store)

    def save(schema: str) -> EvidenceRef:
        return store.put(
            b'{"unit_only":true}',
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="unit-policy",
            ),
        )

    policy = EnabledPolicy(
        status="enabled",
        reason="unit only",
        component_id="memory",
        contract_version="1.0",
        configuration_ref=save("optional-policy-config/1"),
        reviewer_component_id="reviewer",
        reviewer_contract_version="1.0",
        validation_ref=save("optional-policy-validation/1"),
    )
    return RunPlan.model_validate(
        {
            **value.model_dump(),
            "policies": RunPolicies(
                actor_memory=policy, teacher_template=value.policies.teacher_template
            ),
        }
    )


def test_disabled_publish_and_load_never_read_optional_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FileEvidenceStore(tmp_path)
    value = persisted_plan(store)
    reads: list[EvidenceRef] = []
    original_read = store.read

    def read(reference: EvidenceRef, control: OperationControl | None = None) -> bytes:
        assert not reference.content_schema.startswith("optional-policy-")
        reads.append(reference)
        return original_read(reference)

    monkeypatch.setattr(store, "read", read)
    binding = frozen_binding(store, value)
    assert loader(store).load(binding, command()) == value
    assert set(reads) == set(value.references()) | {binding.plan_ref}
    assert loader(store).publish(value, command()) == binding.plan_ref


def test_enabled_inputs_are_checked_and_exact_choice_survives_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FileEvidenceStore(tmp_path)
    value = selected_plan(store)
    binding = frozen_binding(store, value)
    reads: list[EvidenceRef] = []
    original_read = store.read

    def read(reference: EvidenceRef, control: OperationControl | None = None) -> bytes:
        reads.append(reference)
        return original_read(reference)

    monkeypatch.setattr(store, "read", read)
    assert loader(store).load(binding, command()).policies == value.policies
    assert set(value.policies.references()) <= set(reads)
    assert loader(store).publish(value, command()) == binding.plan_ref


@pytest.mark.parametrize("which", ["configuration_ref", "validation_ref"])
def test_missing_selected_input_blocks_both_boundaries_without_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    store = FileEvidenceStore(tmp_path)
    value = selected_plan(store)
    binding = frozen_binding(store, value)
    policy = value.policies.actor_memory
    assert isinstance(policy, EnabledPolicy)
    target = (
        policy.configuration_ref
        if which == "configuration_ref"
        else policy.validation_ref
    )
    original_read = store.read
    writes: list[bytes] = []
    original_put = store.put

    def read(reference: EvidenceRef, control: OperationControl | None = None) -> bytes:
        if reference == target:
            raise EvidenceNotFound("selected input missing")
        return original_read(reference)

    def put(
        data: bytes, metadata: EvidenceMetadata, control: OperationControl | None = None
    ) -> EvidenceRef:
        writes.append(data)
        return original_put(data, metadata)

    monkeypatch.setattr(store, "read", read)
    monkeypatch.setattr(store, "put", put)
    with pytest.raises(EvidenceNotFound):
        loader(store).publish(value, command())
    with pytest.raises(EvidenceNotFound):
        loader(store).load(binding, command())
    assert writes == []

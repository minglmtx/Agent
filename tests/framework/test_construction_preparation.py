"""Original source -> frozen saved Generator work -> original control, no runner."""

from pathlib import Path
from datetime import datetime, timezone
import pytest
from lab_generate_skill.application.construction_preparation import (
    prepare_generator_step,
    GenerationPreparationUnconfirmed,
)
from lab_generate_skill.application.construct_targets import construct_targets
from lab_generate_skill.domain.errors import RevisionConflict, InvalidTransition
from lab_generate_skill.domain.construction_control import GenerateConstructionWork
from lab_generate_skill.domain.local_generator import LocalGeneratorParameters
from construction_preparation_fixtures import preparation_case


def test_original_public_top6_saved_step_read_then_native_once_and_journal(
    tmp_path: Path,
) -> None:
    c = preparation_case(tmp_path / "case")
    request = c.request()
    before = c.control.journal.read(request.operation)
    prepared = prepare_generator_step(request, c.deps)
    assert prepared == prepare_generator_step(request, c.deps)
    assert c.control.journal.read(request.operation) == before
    c.native.assert_no_inference()
    step = prepared.step
    assert isinstance(step.work, GenerateConstructionWork)
    assert len(step.work.request.retrieved_skills) == 6
    assert (
        step.work.request.candidate_index,
        step.work.request.resample_index,
        step.work.request.seed,
        step.work.request.temperature,
    ) == (0, 0, *before.plan.method.generator_sampling(0, 0))
    params = LocalGeneratorParameters.model_validate_json(
        c.native.data.store.read(step.work.planned.call.parameters_ref)
    )
    assert params.max_input_tokens == c.native.parameters.max_input_tokens
    assert params.max_new_tokens == c.native.parameters.max_new_tokens
    assert "private_spec_ref" not in step.work.request.model_dump_json()
    assert "claim_ref" not in step.work.request.model_dump_json()
    read = c.records.load(
        prepared.reference,
        request.run,
        request.operation,
        control=c.control.controls.bind(request.operation),
    )
    assert read == prepared
    actual = construct_targets(read.step, c.control)
    assert (
        actual.status == "advanced"
        and actual.progress.project().next_action.kind == "generate"
    )
    assert actual.progress.project().next_action.candidate_slot == 1
    assert actual.progress.project().next_action.resample_index == 0
    assert len(actual.progress.project().candidates) == 1
    assert c.native.engine.calls == 1
    with pytest.raises(RevisionConflict):
        construct_targets(read.step, c.control)
    assert c.native.engine.calls == 1
    cleanup = request.operation.cleanup(
        "prepared-step-closed-read", now=datetime.now(timezone.utc), seconds=60
    )
    assert (
        c.records.load(
            prepared.reference,
            request.run,
            cleanup,
            control=c.control.controls.bind(cleanup),
        )
        == prepared
    )
    assert c.native.engine.calls == 1


def test_unknown_original_generator_cannot_prepare_new_id_or_reinvoke_saved_step(
    tmp_path: Path,
) -> None:
    from lab_generate_skill.application.construct_targets import (
        ConstructionStepUnconfirmed,
    )

    c = preparation_case(tmp_path / "case")
    request = c.request()
    saved = prepare_generator_step(request, c.deps)
    c.native.engine.failure = OSError("original generation outcome unconfirmed")
    with pytest.raises(ConstructionStepUnconfirmed):
        construct_targets(saved.step, c.control)
    assert c.native.engine.calls == 1
    with pytest.raises(GenerationPreparationUnconfirmed) as caught:
        prepare_generator_step(c.request("new-id-cannot-retry"), c.deps)
    assert (
        isinstance(caught.value.primary, InvalidTransition)
        and not caught.value.retained
    )
    assert construct_targets(saved.step, c.control).status == "waiting"
    assert c.native.engine.calls == 1

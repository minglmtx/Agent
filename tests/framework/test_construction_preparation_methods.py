"""Original four-candidate/resampling rules through the saved-step producer."""

import json
from pathlib import Path
from lab_generate_skill.application.construct_targets import construct_targets
from lab_generate_skill.application.construction_preparation import (
    prepare_generator_step,
)
from lab_generate_skill.domain.construction_control import GenerateConstructionWork
from construction_preparation_fixtures import preparation_case
from test_run_journal import command
from test_construction_state import skill


def test_all_four_original_slots_preserve_sampling_and_top6(tmp_path: Path) -> None:
    c = preparation_case(tmp_path / "case")
    for slot in range(4):
        request = c.request("slot-" + str(slot))
        before = c.control.journal.read(request.operation)
        saved = prepare_generator_step(request, c.deps)
        assert isinstance(saved.step.work, GenerateConstructionWork)
        public = saved.step.work.request
        assert (public.candidate_index, public.resample_index) == (slot, 0)
        assert (
            public.seed,
            public.temperature,
        ) == before.plan.method.generator_sampling(slot, 0)
        assert len(public.retrieved_skills) == 6
        c.native.engine.output = c.native.engine.output.model_copy(
            update={"text": json.dumps(skill("different-" + str(slot)).model_payload())}
        )
        actual = construct_targets(saved.step, c.control)
        assert actual.status == "advanced" and c.native.engine.calls == slot + 1
        current = actual.progress
        assert current.project().next_action.kind == (
            "generate" if slot < 3 else "execute"
        )
    assert len(current.project().candidates) == 4 and not current.project().attempts
    # Only after all four Generator candidates: declared unit Actor closure
    # facts advance the same method; no physical Actor support is inferred.
    for _ in range(8):
        event = c.native.data.event(current)
        current = c.control.journal.append(event, current.revision, event.operation)
    assert current.project().next_action.kind == "revise"
    assert len(current.project().attempts) == 4


def test_duplicate_resampling_keeps_all_five_frozen_attempted_samples(
    tmp_path: Path,
) -> None:
    c = preparation_case(tmp_path / "case")
    first = prepare_generator_step(c.request("original-slot0"), c.deps)
    current = construct_targets(first.step, c.control).progress
    for index in range(5):
        saved = prepare_generator_step(
            c.request("duplicate-slot1-" + str(index)), c.deps
        )
        assert isinstance(saved.step.work, GenerateConstructionWork)
        public = saved.step.work.request
        assert (public.candidate_index, public.resample_index) == (1, index)
        assert (
            public.seed,
            public.temperature,
        ) == current.plan.method.generator_sampling(1, index)
        current = construct_targets(saved.step, c.control).progress
        assert current.project().next_action.kind == "generate"
        assert current.project().next_action.candidate_slot == (1 if index < 4 else 2)
    assert c.native.engine.calls == 6 and len(current.project().candidates) == 2

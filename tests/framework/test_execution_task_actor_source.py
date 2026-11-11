"""Single source per-turn Actor authority on actual journals, unit resource/model effects."""

from dataclasses import replace
from pathlib import Path
import pytest
from lab_generate_skill.application.actor_loop import RecordedActorRunner
from lab_generate_skill.application.execution_task_actor_admission import (
    ExecutionTaskActorAdmissionDeps,
    ExecutionTaskActorAuthority,
)
from lab_generate_skill.application.execute_task import (
    execute_task,
    TaskExecutionUnconfirmed,
)
from lab_generate_skill.domain.actor_admission import PreparedActorInput
from lab_generate_skill.domain.task_execution import InitializedTask
from lab_generate_skill.domain.actor_run import ActorRunRequest
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.actor import ActorRunner
from lab_generate_skill.ports.lifecycle import OperationControl
from execution_task_phase_fixtures import phase_case, SinglePhaseCase
from construction_storage_fixtures import put


class RevocableActorSource:
    def __init__(self) -> None:
        self.calls = 0
        self.revoke_after_first = False

    def verify(
        self, request: ActorRunRequest, trace: TraceSnapshot, control: OperationControl
    ) -> None:
        control.checkpoint()
        self.calls += 1
        if self.revoke_after_first and self.calls > 1:
            raise OwnershipConflict("Original Actor source revoked during turn")


def bind_single(
    f: SinglePhaseCase, root: RevocableActorSource, *, invalid_role_probe: bool = False
) -> None:
    c = f.task
    old = c.deps.actors
    deps = ExecutionTaskActorAdmissionDeps(
        c.deps.source_reader, c.deps.runs, c.deps.claims, c.deps.evidence, root
    )

    class Binding:
        def bind(
            self, initialized: InitializedTask, prepared: PreparedActorInput
        ) -> ActorRunner:
            if invalid_role_probe:
                wire = prepared.model_dump()
                wire.pop("execution_source_ref")
                wire.update(
                    schema_version="prepared-actor-input/1", construction_revision=0
                )
                forged = PreparedActorInput.model_validate(wire)
                with pytest.raises(OwnershipConflict):
                    deps.authority(c.plan, initialized, forged)
            runner = old.bind(initialized, prepared)
            assert isinstance(runner, RecordedActorRunner)
            return RecordedActorRunner(
                replace(
                    runner.deps, authority=deps.authority(c.plan, initialized, prepared)
                )
            )

    c.deps = replace(c.deps, actors=Binding())


def test_single_actor_turn_uses_original_policy_run_handoff_and_actual_source_gate(
    tmp_path: Path,
) -> None:
    f = phase_case(tmp_path / "single")
    root = RevocableActorSource()
    bind_single(f, root, invalid_role_probe=True)
    c = f.task
    result = execute_task(c.plan, c.deps)
    assert (
        result.generations
        == result.interactions
        == c.model.calls
        == c.browser.calls
        == 1
    )
    assert root.calls >= 2 and not hasattr(c.deps, "construction")
    assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]


def test_actor_source_revocation_after_initial_pass_refuses_before_model_and_still_closes(
    tmp_path: Path,
) -> None:
    f = phase_case(tmp_path / "single")
    root = RevocableActorSource()
    root.revoke_after_first = True
    bind_single(f, root)
    c = f.task
    with pytest.raises(TaskExecutionUnconfirmed):
        execute_task(c.plan, c.deps)
    assert root.calls == 2 and c.model.calls == c.browser.calls == 0
    assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]


def test_actor_parameters_cannot_be_substituted_after_source_initial_admission(
    tmp_path: Path,
) -> None:
    f = phase_case(tmp_path / "single")
    c = f.task
    root = RevocableActorSource()
    bind_single(f, root)
    actor = c.phases.initialized.actor
    changed = put(
        c.source.data.store, {"wrong_model_parameters": True}, "model-parameters/1"
    )
    c.phases.initialized = c.phases.initialized.model_copy(
        update={"actor": actor.model_copy(update={"parameters_refs": (changed,)})}
    )
    with pytest.raises(TaskExecutionUnconfirmed):
        execute_task(c.plan, c.deps)
    assert c.model.calls == c.browser.calls == 0
    assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]


def test_current_actor_binding_accepts_source_contract_without_constructing_training_deps() -> (
    None
):
    import subprocess, sys

    program = """
import sys
from lab_generate_skill.bootstrap.task_actor import CurrentTaskActorBinding
from lab_generate_skill.application.execution_task_actor_admission import ExecutionTaskActorAdmissionDeps
assert 'lab_generate_skill.application.task_actor_admission' not in sys.modules
assert 'lab_generate_skill.domain.construction_state' not in sys.modules
"""
    subprocess.run([sys.executable, "-B", "-c", program], check=True)


@pytest.mark.parametrize(
    "fault", ["configuration", "configuration-body", "publication"]
)
def test_retained_actor_bodies_cannot_change_after_original_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    f = phase_case(tmp_path / "single")
    root = RevocableActorSource()
    bind_single(f, root)
    original = ExecutionTaskActorAuthority.verify
    injected: list[str] = []

    def verify(
        self: ExecutionTaskActorAuthority,
        request: ActorRunRequest,
        trace: TraceSnapshot,
        control: OperationControl,
    ) -> None:
        if not injected and self._published_inputs is not None:
            if fault == "publication":
                self._published_inputs = tuple(
                    r.model_copy(update={"producer": "foreign-publication"})
                    for r in self._published_inputs
                )
            elif fault == "configuration":
                assert self._configuration is not None
                ref, config = self._configuration
                self._configuration = (
                    ref.model_copy(update={"producer": "foreign"}),
                    config,
                )
            else:
                assert self._configuration is not None
                ref, config = self._configuration
                first = config.profiles[0]
                self._configuration = (
                    ref,
                    config.model_copy(
                        update={
                            "profiles": (
                                first.model_copy(
                                    update={"soft_target": first.soft_target + 1}
                                ),
                                *config.profiles[1:],
                            )
                        }
                    ),
                )
            injected.append(fault)
        return original(self, request, trace, control)

    monkeypatch.setattr(ExecutionTaskActorAuthority, "verify", verify)
    c = f.task
    with pytest.raises(TaskExecutionUnconfirmed):
        execute_task(c.plan, c.deps)
    assert injected == [fault] and c.model.calls == c.browser.calls == 0
    assert c.phases.calls[-3:] == ["close", "verify_closed", "restore"]

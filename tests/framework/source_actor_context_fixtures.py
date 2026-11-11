"""Real source assembly/CAS/once/native frames; explicit synthetic resource rights.

Allocation/controller/installation and tokenizer/inference below are unit facts.
They do not qualify a source, installed worker, model, website or new request.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.adapters.models.actor_service import ActorService
from lab_generate_skill.adapters.models.actor_worker_client import SupervisedActorEngine
from lab_generate_skill.adapters.models.transformers_actor import ResidentActorEngine
from lab_generate_skill.adapters.models.local_actor_evidence import ActorEvidence
from lab_generate_skill.adapters.models.actor_resource_records import fact
from lab_generate_skill.adapters.slurm.step_launch import actor_step_name
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.actor_step import ActorSlurmBinding, ActorStepStarted
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.slurm_step import SlurmStepTarget, SlurmControllerStep
from lab_generate_skill.domain.local_actor import LocalActorBinding
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
)
from lab_generate_skill.domain.browser import BrowserAction, StepResult
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_engine_fixtures import setup as engine_setup
from actor_installation_fixtures import unit_declaration, unit_verifier
from actor_worker_fixtures import UnitChannel, unit_guard
from actor_context_projection_fixtures import actor_projection_case
from allocation_fixtures import Case as AllocationCase
from test_slurm_probe import operation
from test_source_actor_assembly import setup
from state_contract_fixtures import recovery


class UnitSourceSession:
    def __init__(self, source: Any, initial: EvidenceRef) -> None:
        self.source = source
        self.observation_ref = initial
        self.engine = SimpleNamespace(state="ready")
        self.calls = 0

    def step(
        self, action: BrowserAction, op: OperationContext, *, control: OperationControl
    ) -> StepResult:
        self.calls += 1
        n = self.source.native
        before = self.observation_ref
        observed = Observation.model_validate_json(
            self.source.c.evidence.read(before, control)
        )
        observed = observed.model_copy(
            update={
                "sequence": observed.sequence + 1,
                "observation_id": "source-after-" + str(self.calls),
            }
        )
        reference = self.source.c.evidence.put(
            observed.model_dump_json().encode(),
            EvidenceMetadata.model_validate(
                before.model_dump(
                    include={"media_type", "content_schema", "visibility", "producer"}
                )
            ),
            control=control,
        )
        scope = self.source.saved["baseline_inputs"].prepared.scope
        returned = BrowserReadout(
            scope=scope,
            operation=op,
            action=action,
            observation=observed,
            events=(),
            environment_reward=0.0,
            terminated=False,
            truncated=False,
            protocol_terminal=True,
        )
        raw = n.raw(returned.model_dump_json().encode(), "browser-step-return/1")
        self.observation_ref = reference
        self.engine.state = "terminal"
        return StepResult(
            scope=scope,
            operation=op,
            action_id=action.action_id,
            before_observation_ref=before,
            observation_ref=reference,
            return_ref=raw,
            terminal=True,
        )


def source_context_case(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    engine_config: ActorEngineConfig | None = None,
) -> Any:
    root.mkdir()
    source, browser, actor, params, state, journal = setup(root)
    worker_root = root / "unit-worker"
    worker_root.mkdir()
    old, loader, _, _, control = engine_setup(worker_root)
    config = (
        old.config.model_copy(update={"context_window": 32768})
        if engine_config is None
        else ActorEngineConfig.model_validate(engine_config)
    )
    if config.long_context is not None:
        params = params.model_copy(
            update={
                "max_input_tokens": config.context_window - 4096,
                "max_new_tokens": 4096,
            }
        )
    engine = ResidentActorEngine(old.artifact, config, loader=loader)
    channel = UnitChannel(
        ActorService(lambda artifact, config: engine, unit_verifier, unit_guard)
    )
    client = SupervisedActorEngine(
        channel, "session", engine.artifact, config, unit_declaration()
    )
    client.configure(control)
    guard, installed = client.owner_guard, client.installed_sources
    assert guard is not None and installed is not None
    native = source.native
    # Storage-only sample actions are not an Actor protocol fixture. Freeze the
    # explicit supported unit actions and their original public-task binding.
    native.public = native.public.model_copy(
        update={"allowed_actions": ("click", "send_msg_to_user")}
    )
    public_ref = actor.evidence.put(
        native.public.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="public-task/1",
            visibility="public",
            producer="unit-source-context",
        ),
    )
    native.binding = TaskBinding.model_validate(
        native.binding.model_copy(update={"public_task_ref": public_ref})
    )
    native.binding_ref = native.put(native.binding)
    release_ref = native.put(unit_declaration().manifest)
    model = ActorModelBinding(
        model="unit/source-qwen2",
        release_ref=release_ref,
        component_id="actor",
        model_artifact_id=engine.artifact.artifact_id,
        engine_config_artifact_id="actor-config",
        engine_config_ref=native.put(config),
    )
    model_ref = native.raw(model.model_dump_json().encode(), "model-binding/1")
    allocation_root = root / "unit-allocation"
    allocation_root.mkdir()
    allocation_case = AllocationCase(allocation_root, monkeypatch)
    allocation = allocation_case.verifier().observe(
        allocation_case.execution, allocation_case.writer, operation()
    )
    facts = allocation.facts.model_copy(
        update={
            "writer": guard.controller,
            "controller": allocation.facts.controller.model_copy(
                update={"node_id": guard.controller.node_id}
            ),
            "cgroup": allocation.facts.cgroup.model_copy(
                update={"writer": guard.controller}
            ),
        }
    )
    allocation = allocation.model_copy(update={"facts": facts})
    owner = state.baseline.scope.owner.model_copy(
        update={"job_id": facts.execution.job_id}
    )
    scope = state.baseline.scope.model_copy(update={"owner": owner})
    token = actor.spec.token.model_copy(
        update={
            "owner": owner,
            "expected_resource_id": client.session_id,
            "recovery_ref": native.put(
                recovery(False).model_copy(update={"owner": owner})
            ),
        }
    )
    actor.spec = ActorResourceSpec(
        token=token,
        release_ref=release_ref,
        model_binding_ref=model_ref,
        python_executable=installed.executable,
        slurm=ActorSlurmBinding(
            allocation=allocation,
            srun_executable="/usr/bin/srun",
            scontrol_executable="/usr/bin/scontrol",
        ),
        artifact=engine.artifact,
        engine_config=config,
    )
    actor.op = actor.op.model_copy(
        update={
            "allocation_id": token.allocation_id,
            "recovery_ref": token.recovery_ref,
        }
    )
    actor.clock = allocation_case.clock
    source.c.spec.token = source.c.spec.token.model_copy(
        update={"owner": owner, "recovery_ref": token.recovery_ref}
    )
    browser.spec.token = browser.spec.token.model_copy(
        update={
            "owner": owner,
            "recovery_ref": native.put(
                recovery(True).model_copy(update={"owner": owner})
            ),
        }
    )
    prepared = state.baseline_inputs.prepared.model_copy(
        update={
            "scope": scope,
            "public_task": native.public,
            "task_binding_ref": native.binding_ref,
        }
    )
    baseline = state.baseline.model_copy(
        update={"scope": scope, "prepared_ref": native.put(prepared)}
    )
    source.saved.update(
        baseline=baseline,
        baseline_ref=native.put(baseline),
        baseline_inputs=SimpleNamespace(
            observation_ref=state.baseline_inputs.observation_ref,
            prepared=SimpleNamespace(scope=scope),
        ),
    )
    worker_cgroup = facts.cgroup.model_copy(
        update={
            "step_id": "0",
            "user_path": "/sys/fs/cgroup/system.slice/slurmstepd.scope/job_"
            + owner.job_id
            + "/step_0/user",
            "writer": guard.worker,
        }
    )
    target = SlurmStepTarget(
        execution=facts.execution,
        step_name=actor_step_name(token),
        resources="single_gpu",
        launcher=guard.supervisor,
        worker=worker_cgroup,
    )
    started = ActorStepStarted(
        allocation=allocation,
        controller=SlurmControllerStep(
            target=target,
            started_at_epoch=facts.execution.started_at_epoch,
            gpu_type=facts.controller.gpu_type,
            memory="1G",
        ),
        evidence=native.raw(b"{}", "actor-step-raw/1"),
    )
    acquired = fact(
        actor.evidence,
        actor.spec,
        actor.op,
        "acquired",
        dict(
            owner_guard=guard.model_dump(mode="json"),
            worker=guard.worker.model_dump(mode="json"),
            installed_sources=installed.model_dump(mode="json"),
            step=started.model_dump(mode="json"),
        ),
        control,
    )
    binding = LocalActorBinding(
        resource=token,
        release_ref=release_ref,
        model_binding_ref=model_ref,
        spec_ref=native.put(actor.spec),
        acquired_ref=acquired,
        cleanup_seconds=15,
    )
    resource_calls: list[bool] = []

    def require_original(
        value: LocalActorBinding,
        op: OperationContext,
        control: OperationControl,
        *,
        live: bool,
    ) -> None:
        control.checkpoint()
        assert value == binding
        resource_calls.append(live)

    model_scope: Any = SimpleNamespace(
        spec=actor.spec,
        binding=binding,
        engine=client,
        guard=guard,
        evidence=ActorEvidence(actor.evidence),
        require_original=require_original,
    )
    session = UnitSourceSession(source, state.baseline_inputs.observation_ref)
    loader.session.output = loader.session.output.model_copy(
        update={"text": '{"action":"send_msg_to_user(\'Done\')"}'}
    )
    return SimpleNamespace(
        source=source,
        browser=browser,
        actor=actor,
        params=params,
        state=state,
        journal=journal,
        loader=loader,
        client=client,
        channel=channel,
        scope=model_scope,
        session=session,
        policy=actor_projection_case().policy.model_copy(
            update={
                "software_evidence_ref": native.raw(
                    b'{"synthetic_software_gate_only":true,"source_permission":false}',
                    "context-policy-evidence/1",
                )
            }
        ),
        resource_calls=resource_calls,
    )

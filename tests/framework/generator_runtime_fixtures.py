"""Synthetic worker/process probes; real CAS and invocation/resource contracts.

Only the separate actual-resource and GPU cases establish live worker behavior.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.adapters.models import generator_execution_scope as scope_module
from lab_generate_skill.adapters.models.generator_execution_scope import (
    GeneratorExecutionScope,
)
from lab_generate_skill.adapters.models.generator_execution_authority import (
    ResourceGeneratorExecutionAuthority,
)
from lab_generate_skill.adapters.models.generator_invocation import (
    ResourceGeneratorInvocation,
)
from lab_generate_skill.adapters.models.generator_worker_client import (
    SupervisedGeneratorEngine,
)
from lab_generate_skill.adapters.models.generator_worker_exchange import (
    GeneratorWorkerExchange,
)
from lab_generate_skill.adapters.models.generator_worker_protocol import (
    GeneratorWorkerCommand,
    GeneratorWorkerReply,
)
from lab_generate_skill.adapters.models.local_generator import DurableGeneratorInference
from lab_generate_skill.adapters.models.local_generator_evidence import local_metadata
from lab_generate_skill.domain.release_installation import InstalledReleaseModule
from lab_generate_skill.domain.generator_installation import (
    GeneratorInstalledSources,
)
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorParameters,
    LocalGeneratorOutput,
)
from lab_generate_skill.domain.lifecycle import (
    ResourceRecord,
    ResourceState,
    ResourceEvent,
    OperationContext,
    AllocationToken,
)
from lab_generate_skill.ports.lifecycle import OperationControl, ResourceJournal
from generator_execution_fixtures import (
    ExecutionCase,
    e as e,
    execution_template as execution_template,
)
from local_generator_fixtures import case, Case


class Journal:
    def __init__(self, record: ResourceRecord) -> None:
        self.record = record

    def read(self, token: AllocationToken, op: OperationContext) -> ResourceRecord:
        assert token == self.record.token
        assert (op.allocation_id, op.recovery_ref) == (
            token.allocation_id,
            token.recovery_ref,
        )
        return self.record


class SyntheticWorker:
    def __init__(self, e: ExecutionCase, spec: GeneratorResourceSpec) -> None:
        self.owner_guard = e.record.guard
        self.installed_sources = GeneratorInstalledSources(
            release_id="synthetic",
            manifest_sha256=spec.release_ref.sha256,
            executable=spec.python_executable,
            package_root="/test/lab_generate_skill",
            distribution_version="0.1",
            modules=(
                InstalledReleaseModule(
                    name="lab_generate_skill",
                    filename="/test/lab_generate_skill/__init__.py",
                ),
            ),
        )
        self.session = spec.token.expected_resource_id
        self.calls = 0
        self.output = e.output
        self.failure: BaseException | None = None

    def validate(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> None:
        control.checkpoint()

    def generate_exchange(
        self,
        request: GeneratorModelRequest,
        parameters: LocalGeneratorParameters,
        control: OperationControl,
    ) -> GeneratorWorkerExchange:
        self.calls += 1
        if self.failure:
            raise self.failure
        command = GeneratorWorkerCommand(
            session_id=self.session,
            sequence=2 + self.calls,
            operation="generate",
            remaining_seconds=control.checkpoint(),
            request=request,
            parameters=parameters,
        )
        reply = GeneratorWorkerReply(
            session_id=self.session,
            sequence=command.sequence,
            operation="generate",
            command_sha256=command.digest,
            status="ok",
            output=self.output,
        )
        return GeneratorWorkerExchange(
            command.model_dump_json().encode(), reply.model_dump_json().encode()
        )


@dataclass
class RuntimeCase:
    e: ExecutionCase
    local: Case
    scope: GeneratorExecutionScope
    journal: Journal
    worker: SyntheticWorker

    @property
    def actual(self) -> ResourceGeneratorExecutionAuthority:
        return ResourceGeneratorExecutionAuthority(self.scope, self.e.adapter)

    @property
    def adapter(self) -> DurableGeneratorInference:
        return DurableGeneratorInference(
            self.local.root,
            self.scope.binding,
            ResourceGeneratorInvocation(self.scope, self.e.adapter),
            self.e.store,
            self.local.controls,
            self.actual,
        )

    def close(self) -> None:
        last = self.journal.record.events[-1]
        cleanup = self.local.cleanup.model_copy(
            update={
                "allocation_id": self.scope.spec.token.allocation_id,
                "recovery_ref": self.scope.spec.token.recovery_ref,
            }
        )
        events = tuple(
            ResourceEvent(
                state=cast(ResourceState, state),
                operation=cleanup.model_copy(update={"operation_id": state}),
                evidence=last.evidence,
            )
            for state in ("closing", "closed")
        )
        self.journal.record = ResourceRecord(
            token=self.scope.spec.token, events=(*self.journal.record.events, *events)
        )


@pytest.fixture
def runtime(
    e: ExecutionCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> RuntimeCase:
    spec = GeneratorResourceSpec.model_validate_json(e.store.read(e.record.spec_ref))
    worker = SyntheticWorker(e, spec)
    raw = json.loads(e.store.read(e.record.acquired_ref))
    raw["installed_sources"] = worker.installed_sources.model_dump(mode="json")
    acquired = e.put(json.dumps(raw).encode(), "generator-resource-fact/1")
    operation = OperationContext.model_validate_json(json.dumps(raw["operation"]))
    events = tuple(
        ResourceEvent(
            state=cast(ResourceState, state),
            operation=operation.model_copy(update={"operation_id": state}),
            evidence=(e.put(b"intent", "resource-acquisition-intent/1"),),
        )
        for state in ("registered", "acquiring")
    )
    journal = Journal(
        ResourceRecord(
            token=spec.token,
            events=(
                *events,
                ResourceEvent(
                    state="acquired", operation=operation, evidence=(acquired,)
                ),
            ),
        )
    )
    root = tmp_path / "local"
    root.mkdir()
    local = case(root)
    local.binding = e.record.intent.binding
    local.operation = e.record.intent.operation
    local.request = GeneratorModelRequest.model_validate_json(
        e.store.read(e.record.intent.request_ref)
    )

    def identity(readings: object, pid: int, uid: int) -> object:
        return next(
            x
            for x in (worker.owner_guard.supervisor, worker.owner_guard.worker)
            if x.process_id == pid
        )

    monkeypatch.setattr(scope_module, "read_process_identity", identity)
    scope = GeneratorExecutionScope(
        local.binding,
        spec,
        cast(ResourceJournal, journal),
        e.store,
        cast(SupervisedGeneratorEngine, worker),
        local.operation,
        local.controls.bind(local.operation),
    )
    return RuntimeCase(e, local, scope, journal, worker)

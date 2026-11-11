"""Validate actual original wire bytes and their acquired-resource provenance.

No live rights or trust from self-reported metadata: the producing runtime must
be independently admitted. This reader validates content consistency, including
original request/parameters, resource spec, installed guard and worker identity.
"""

import hashlib
import json
from lab_generate_skill.domain.generator_execution import GeneratorExecutionRecord
from lab_generate_skill.domain.generator_resource import GeneratorResourceSpec
from lab_generate_skill.domain.generator_step import GeneratorStepStarted
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.local_generator import LocalGeneratorOutput
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.processes.wire_json import json_object
from .generator_worker_protocol import (
    decode_command,
    decode_reply,
    validate_worker_output,
    MAX_WORKER_PACKET,
)
from .local_generator_evidence import LocalGeneratorEvidence
from .generator_step import same_allocation
from .generator_resource_records import check_operation
from lab_generate_skill.adapters.slurm.step_launch import generator_step_name
from lab_generate_skill.domain.lifecycle import OperationContext


def read_exact(
    store: EvidenceStore, reference: EvidenceRef, limit: int, control: OperationControl
) -> bytes:
    if reference.size_bytes > limit:
        raise EvidenceIntegrityError("Generator execution evidence exceeds read bound")
    control.checkpoint()
    raw = store.read(reference, control=control)
    control.checkpoint()
    if type(raw) is not bytes or (len(raw), hashlib.sha256(raw).hexdigest()) != (
        reference.size_bytes,
        reference.sha256,
    ):
        raise EvidenceIntegrityError("Generator execution evidence identity differs")
    return raw


def verify_execution(
    store: EvidenceStore, record: GeneratorExecutionRecord, control: OperationControl
) -> LocalGeneratorOutput:
    record = GeneratorExecutionRecord.model_validate(record)
    spec_raw = read_exact(store, record.spec_ref, 8 * 1024 * 1024, control)
    json_object(spec_raw)
    spec = GeneratorResourceSpec.model_validate_json(spec_raw)
    if spec.model_dump_json().encode() != spec_raw:
        raise EvidenceIntegrityError("Noncanonical Generator resource spec")
    binding = record.intent.binding
    if (
        spec.token,
        spec.release_ref,
        spec.model_binding_ref,
        spec.slurm.allocation.facts.writer,
    ) != (
        record.resource,
        binding.release_ref,
        binding.model_binding_ref,
        record.guard.controller,
    ):
        raise EvidenceIntegrityError("Execution differs from original resource scope")
    acquired = json_object(
        read_exact(store, record.acquired_ref, 16 * 1024 * 1024, control)
    )
    if (
        acquired.get("schema_version"),
        acquired.get("kind"),
        acquired.get("spec_sha256"),
        acquired.get("token"),
        acquired.get("owner_guard"),
    ) != (
        "generator-resource-fact/1",
        "acquired",
        record.spec_ref.sha256,
        record.resource.model_dump(mode="json"),
        record.guard.model_dump(mode="json"),
    ):
        raise EvidenceIntegrityError("Execution acquired resource evidence differs")
    started = GeneratorStepStarted.model_validate_json(json.dumps(acquired.get("step")))
    same_allocation(spec.slurm.allocation, started.allocation)
    check_operation(
        spec,
        OperationContext.model_validate_json(json.dumps(acquired.get("operation"))),
        "execute",
    )
    if (
        started.controller.target.worker.writer != record.guard.worker
        or acquired.get("worker") != record.guard.worker.model_dump(mode="json")
        or started.controller.target.step_name != generator_step_name(record.resource)
    ):
        raise EvidenceIntegrityError("Execution worker differs from original step")
    command = decode_command(
        read_exact(store, record.command_ref, MAX_WORKER_PACKET, control)
    )
    reply = decode_reply(
        command, read_exact(store, record.reply_ref, MAX_WORKER_PACKET, control)
    )
    if (
        command.session_id != spec.token.expected_resource_id
        or command.operation != "generate"
        or reply.status != "ok"
        or command.request is None
        or command.parameters is None
        or reply.output is None
    ):
        raise EvidenceIntegrityError(
            "Execution needs a successful original generate reply"
        )
    request_raw = command.request.model_dump_json().encode()
    if (
        command.request.request_id,
        len(request_raw),
        hashlib.sha256(request_raw).hexdigest(),
    ) != (
        record.intent.request_id,
        record.intent.request_ref.size_bytes,
        record.intent.request_ref.sha256,
    ):
        raise EvidenceIntegrityError("Execution request differs from original intent")
    if (
        read_exact(store, record.intent.request_ref, MAX_WORKER_PACKET, control)
        != request_raw
    ):
        raise EvidenceIntegrityError("Execution request bytes differ")
    params = LocalGeneratorEvidence(store).parameters(binding, command.request, control)
    raw = params.model_dump_json().encode()
    if (
        command.parameters != params
        or read_exact(store, record.intent.parameters_ref, 16384, control) != raw
    ):
        raise EvidenceIntegrityError("Execution parameters differ from original intent")
    control.checkpoint()
    return validate_worker_output(reply.output, params)

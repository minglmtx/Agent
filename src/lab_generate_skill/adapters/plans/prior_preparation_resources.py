"""Read exact original physical endings; do not settle or close old journals."""

import json
from lab_generate_skill.adapters.models.actor_step import same_allocation
from lab_generate_skill.adapters.slurm.worker_evidence import WorkerStepEvidence
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.actor_step import ActorStepStarted
from lab_generate_skill.domain.ended_stage_preparation import (
    EndedPreparationStageEvidence,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.domain.execution_task_source import ExecutionTaskSource
from lab_generate_skill.domain.lifecycle import ResourceRecord
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.site_resource import (
    SiteResourceReady,
    SiteResourceSpec,
    SiteStepClosed,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from .stage_parent import RetainedStageParentChecks
from .state_reads import StateReads


def _acquisition(
    reads: StateReads, record: ResourceRecord, control: OperationControl
) -> ResourceAcquisitionIntent:
    if (
        len(record.events) < 3
        or record.events[1].state != "acquiring"
        or record.events[2].state != "acquired"
        or len(record.events[1].evidence) != 1
        or len(record.events[2].evidence) != 1
    ):
        raise OwnershipConflict("Original registered acquisition is incomplete")
    intent = reads.parse(
        record.events[1].evidence[0],
        "resource-acquisition-intent/1",
        ResourceAcquisitionIntent,
        control,
    )
    if intent.token != record.token or intent.operation != record.events[1].operation:
        raise OwnershipConflict("Original acquisition changed its resource or writer")
    return intent


def verify_preparation_resources(
    parent: RetainedStageParentChecks,
    inputs: EndedPreparationStageEvidence,
    source: ExecutionTaskSource,
    actor: ResourceRecord,
    site: ResourceRecord,
    session: EvidenceSessionSnapshot,
    control: OperationControl,
) -> SlurmExecutionIdentity:
    """Return the original execution identity; no permission or ledger mutation."""
    reads = parent.reads
    for record, kind in ((actor, "actor"), (site, "site")):
        if (
            record.token.owner != source.run.owner
            or record.token.resource_kind != kind
            or record.token.scope != "batch"
            or record.token.attempt_id is not None
        ):
            raise OwnershipConflict("Preparation resources changed original scope")
    if site.state != "closing" or actor.state not in ("closed", "acquired"):
        raise OwnershipConflict("Unsupported original preparation cleanup state")
    site_intent = _acquisition(reads, site, control)
    site_spec = reads.parse(
        site_intent.configuration_ref, "site-resource-spec/1", SiteResourceSpec, control
    )
    site_fact = json.loads(reads.read(site.events[2].evidence[0], control))
    ready = SiteResourceReady.model_validate_json(
        json.dumps(site_fact["details"]["ready"])
    )
    target = ready.controller.target
    disposition = json.loads(reads.read(inputs.site_disposition_ref, control))
    closed = SiteStepClosed.model_validate_json(json.dumps(disposition["step"]))
    if (
        site_spec.token != site.token
        or site_spec.configuration.installation.manifest_ref != source.run.release_ref
        or site_fact["token"] != site.token.model_dump(mode="json")
        or site_fact["spec_sha256"] != site_intent.configuration_ref.sha256
        or site_fact["operation"] != site.events[2].operation.model_dump(mode="json")
        or disposition.get("schema_version") != "claimed-site-disposition/1"
        or disposition.get("token") != site.token.model_dump(mode="json")
        or disposition.get("node_root") != site_spec.configuration.files.node_root
        or disposition.get("residual_files") != "retained_private_no_reuse"
        or closed.target != target
        or target.execution != site_spec.slurm.execution
        or closed.quiescence.writer_status not in ("missing", "reused")
    ):
        raise OwnershipConflict("Original private site ending/isolation is unconfirmed")
    WorkerStepEvidence("site").require(
        reads.store, closed.evidence, target, "closed", control
    )
    actor_intent = _acquisition(reads, actor, control)
    actor_spec = reads.parse(
        actor_intent.configuration_ref,
        "actor-resource-spec/1",
        ActorResourceSpec,
        control,
    )
    if (
        actor_spec.token != actor.token
        or actor_spec.release_ref != source.run.release_ref
        or actor_spec.slurm.allocation.facts.execution != target.execution
    ):
        raise OwnershipConflict("Actor acquisition changed original execution/release")
    unresolved = [entry for entry in session.entries if not entry.reusable]
    if actor.state == "closed":
        if unresolved or inputs.process_observation_ref is not None:
            raise OwnershipConflict(
                "Closed Actor branch requires settled original reads"
            )
        parent.verify_closed_resource(actor, control)
        return target.execution
    if inputs.process_observation_ref is None or len(unresolved) != 1:
        raise OwnershipConflict("Unclosed Actor requires exact original readback")
    entry = unresolved[0]
    if (
        entry.intent.kind != "read"
        or entry.outcome is not None
        or entry.intent.reference.content_schema != "site-step-raw/1"
        or entry is not session.entries[-1]
    ):
        raise OwnershipConflict("Only the last original site-close read may be unknown")
    # A completed read below is an independent consumption of immutable bytes,
    # not an outcome or settlement of the original unknown operation.
    WorkerStepEvidence("site").require(
        reads.store, entry.intent.reference, target, "closed", control
    )
    fact = json.loads(reads.read(actor.events[2].evidence[0], control))
    started = ActorStepStarted.model_validate_json(json.dumps(fact["step"]))
    same_allocation(actor_spec.slurm.allocation, started.allocation)
    if (
        fact["token"] != actor.token.model_dump(mode="json")
        or fact["spec_sha256"] != actor_intent.configuration_ref.sha256
        or entry.intent.controller != started.allocation.facts.writer
    ):
        raise OwnershipConflict("Original Actor/read controller identities changed")
    proof = json.loads(reads.read(inputs.process_observation_ref, control))
    expected = {
        "actor_" + name: fact["owner_guard"][name]
        for name in ("controller", "supervisor", "worker")
    }
    expected["actor_launcher"] = started.controller.target.launcher.model_dump(
        mode="json"
    )
    expected["original_controller"] = entry.intent.controller.model_dump(mode="json")
    expected["metadata_worker"] = entry.intent.worker.model_dump(mode="json")
    observations = proof.get("processes", [])
    if (
        proof.get("schema_version") != "held-terminal-process-readback/1"
        or proof.get("original_job") != target.execution.job_id
        or proof.get("member", {}).get("sha256") != inputs.member_ref.sha256
        or proof.get("session", {}).get("sha256") != inputs.session_ref.sha256
        or proof.get("actor_resource", {}).get("sha256")
        != inputs.actor_resource_ref.sha256
        or proof.get("original_unknown_retained") is not True
        or proof.get("original_actor_resource_state") != actor.state
        or proof.get("original_writes_or_signals_or_replays") != 0
        or proof.get("runtime_or_training_grant") is not False
        or proof.get("actor_cgroup")
        != {
            "original": started.controller.target.worker.model_dump(mode="json"),
            "exists": False,
        }
        or len(observations) != len(expected)
        or {o.get("name") for o in observations} != set(expected)
        or any(
            o.get("identity") != expected[o["name"]]
            or o.get("observation")
            not in ("missing", "pid_reused", "original_boot_ended")
            for o in observations
        )
    ):
        raise OwnershipConflict(
            "Original process/cgroup inspection is incomplete or changed"
        )
    control.checkpoint()
    return target.execution

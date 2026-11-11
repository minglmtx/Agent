"""Existing fixed graph worker reads retained original Actor bytes, no replay."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.domain.closed_source_read import (
    ClosedMapReadMaterial,
    ClosedSourceReadCommand,
)
from lab_generate_skill.domain.lifecycle import ResourceRecord
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.local_actor import LocalActorBinding
from lab_generate_skill.domain.actor_acquisition_inputs import ActorAcquisitionInputs
from lab_generate_skill.domain.errors import OwnershipConflict, InvalidTransition
from lab_generate_skill.adapters.plans.closed_actor_inputs import (
    SupervisedActorAcquisitionReads,
)
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadFailure,
)
from lab_generate_skill.adapters.plans.closed_source_protocol import (
    decode_command,
    encode_command,
    ClosedSourceReadReply,
)
from lab_generate_skill.adapters.storage.readonly_evidence import ReadOnlyEvidence
from closed_source_read_fixtures import actual_read_case
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from test_slurm_commands import guard
from test_closed_source_read_protocol import E


def retained() -> tuple[ClosedMapReadMaterial, Path, ActorAcquisitionInputs]:
    root = E / "production-4923741"
    material = ClosedMapReadMaterial.model_validate_json(
        (root / "source-read/closed-declarations.json").read_bytes()
    )
    result = json.loads((root / "member-result.json").read_bytes())
    record = ResourceRecord.model_validate_json(
        json.dumps(result["actor_resource_record"])
    )
    intent_ref = next(e for e in record.events if e.state == "acquiring").evidence[0]
    acquired_ref = next(e for e in record.events if e.state == "acquired").evidence[0]
    evidence = ReadOnlyEvidence(root / "evidence", max_object_bytes=64 * 1024**2)
    intent = ResourceAcquisitionIntent.model_validate_json(
        evidence.read(intent_ref, guard(30))
    )
    from lab_generate_skill.domain.actor_resource import ActorResourceSpec

    spec = ActorResourceSpec.model_validate_json(
        evidence.read(intent.configuration_ref, guard(30))
    )
    binding = LocalActorBinding(
        resource=spec.token,
        release_ref=spec.release_ref,
        model_binding_ref=spec.model_binding_ref,
        spec_ref=intent.configuration_ref,
        acquired_ref=acquired_ref,
        cleanup_seconds=15,
    )
    return (
        material,
        root / "evidence",
        ActorAcquisitionInputs(binding=binding, intent_ref=intent_ref),
    )


def test_installed_repeat_exact_bodies_and_no_historical_permission_grant(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    material, root, selection = retained()
    c = actual_read_case(tmp_path, installed_sources, retained=(material, root))
    before = {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    original = None
    successes: list[dict[str, object]] = []
    for _ in range(2):
        c.transport.read(material, guard(60), actor_inputs=selection)
        reply = c.transport.last_reply
        assert reply is not None and reply.actor_bodies is not None
        assert reply.schema_version == "closed-source-read-reply/3"
        assert original is None or reply.actor_bodies == original
        original = reply.actor_bodies
        successes.append(
            {
                "kind": c.transport.timings[-1][0],
                "seconds": c.transport.timings[-1][1],
                "logical_reads": reply.read_count,
                "body_reads": reply.body_read_count,
                "unique_objects": reply.unique_objects,
            }
        )
        assert c.transport.last_request is not None
        command = decode_command(c.transport.last_request)
        assert (
            command.actor_inputs == selection
            and encode_command(command) == c.transport.last_request
        )
        for change in (
            {"kind": "context"},
            {"actor_inputs": None},
            {"binding": None},
            {"execution_plan": None},
        ):
            with pytest.raises(ValueError):
                ClosedSourceReadCommand.model_validate(
                    {**command.model_dump(), **change}
                )
        with pytest.raises(ValueError):
            ClosedSourceReadReply.model_validate(
                {**reply.model_dump(), "schema_version": "closed-source-read-reply/1"}
            )
        with pytest.raises(ValueError):
            ClosedSourceReadReply.model_validate(
                {**reply.model_dump(), "actor_bodies": None}
            )
    assert len(c.transport.timings) == 2
    import os

    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"])
        / "actor-acquisition-body-read-counts.json"
    ).write_text(
        json.dumps(
            {
                "historical_job": 4923741,
                "successes": successes,
                "proofs_for_two_calls": 2,
                "complete_bodies_per_proof": 3,
                "parent_managed_leaf_exchanges_for_these_bodies": 0,
                "scope": "Actual installed fixed reader on original immutable retained graph; not live Actor/current original owner permission or production speedup",
                "runtime_or_training_grant": False,
            },
            indent=2,
        )
        + "\n"
    )
    # Historical immutable facts remain inspectable, never new owner authority.
    reader = SupervisedActorAcquisitionReads(material, c.transport)
    oversized = selection.model_copy(
        update={
            "intent_ref": selection.intent_ref.model_copy(
                update={"size_bytes": 2 * 1024**2 + 1}
            )
        }
    )
    assert reader.read_original(oversized, c.op, guard(60)) is None
    with pytest.raises(OwnershipConflict):
        reader.read_original(selection, c.op, guard(60))
    assert len(c.transport.timings) == 2
    missing = selection.intent_ref.model_copy(
        update={"sha256": "0" * 64, "uri": "cas://sha256/" + "0" * 64}
    )
    with pytest.raises(ClosedSourceReadFailure):
        c.transport.read(
            material,
            guard(60),
            actor_inputs=selection.model_copy(update={"intent_ref": missing}),
        )
    assert (
        c.transport.last_reply is not None
        and c.transport.last_reply.actor_bodies is None
    )
    c.current.admission.stop_new_io()
    with pytest.raises(InvalidTransition):
        c.transport.read(material, guard(60), actor_inputs=selection)
    assert before == {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}

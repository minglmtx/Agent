"""Actual installed guarded whole-graph read, without site/model/task effects.

Original source8671 is read under a distinct actual review controller. Its old
identity is retained; the production same-owner ContextRecords adapter refuses
to use that historical result as a source for this new job.
"""

import json
import os
from pathlib import Path
import time
import pytest
from closed_source_read_fixtures import actual_read_case
from test_closed_source_read_protocol import proposed_source, proposed_material
from lab_generate_skill.bootstrap.map_closed_source import ClosedMapSourceContexts
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.plans.closed_source_records import (
    SupervisedClosedSourceContexts,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def test_actual_original_full_source_read_retains_history_and_rejects_retagging(
    tmp_path: Path,
    installed_sources: InstalledFixture,
) -> None:
    case = actual_read_case(tmp_path, installed_sources)
    material, current, scope, op, controls, transport = (
        case.material,
        case.current,
        case.scope,
        case.op,
        case.controls,
        case.transport,
    )
    owner = scope.binding.owner
    before = {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    started = time.monotonic()
    try:
        receipt = transport.read(material, controls.bind(op))
    finally:
        output = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
        if output and transport.last_capture is not None:
            (Path(output) / "closed-source-read.stdout").write_bytes(
                transport.last_capture.stdout
            )
            (Path(output) / "closed-source-read.stderr").write_bytes(
                transport.last_capture.stderr
            )
    elapsed = time.monotonic() - started
    assert transport.last_reply is not None
    context_reads = transport.last_reply.read_count
    context_objects = transport.last_reply.unique_objects
    assert context_reads >= context_objects > 0
    publication = proposed_source(material, Path(scope.config.evidence_root))
    publication_started = time.monotonic()
    publication_material = proposed_material(material, publication)
    try:
        checked = transport.read(
            publication_material, controls.bind(op), publication=publication
        )
    finally:
        if output := os.environ.get("LAB_JOB_OUTPUT_DIRECTORY"):
            if transport.last_capture is not None:
                (Path(output) / "closed-source-publication.stdout").write_bytes(
                    transport.last_capture.stdout
                )
                (Path(output) / "closed-source-publication.stderr").write_bytes(
                    transport.last_capture.stderr
                )
    publication_elapsed = time.monotonic() - publication_started
    assert checked == publication.context and checked.scope == receipt.scope
    assert (
        transport.last_reply is not None and transport.last_reply.publication_verified
    )
    publication_reply = transport.last_reply
    assert elapsed < 60 and publication_elapsed < 60
    assert (
        transport.last_capture is not None
        and transport.last_capture.termination is not None
    )
    assert transport.last_capture.termination.state == "reaped"
    if output := os.environ.get("LAB_JOB_OUTPUT_DIRECTORY"):
        (Path(output) / "closed-source-publication.stdout").write_bytes(
            transport.last_capture.stdout
        )
        (Path(output) / "closed-source-publication.stderr").write_bytes(
            transport.last_capture.stderr
        )
    assert receipt.scope.owner == material.site.token.owner != owner
    assert {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()} == before
    same = ClosedMapSourceContexts(
        SupervisedClosedSourceContexts(material, transport, controls),
        material.context_ref,
    )
    assert isinstance(same, ClosedMapSourceContexts)
    with pytest.raises(OwnershipConflict, match="retag"):
        same.load_context(material.context_ref, op)
    current.admission.stop_new_io()
    with pytest.raises(InvalidTransition):
        transport.read(material, controls.bind(op))
    assert current.store.state == "ready"
    output = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
    if output:
        (Path(output) / "closed-source-read-actual.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "whole_graph_seconds": elapsed,
                    "publication_validation_seconds": publication_elapsed,
                    "complete_read_calls": context_reads,
                    "unique_read_objects": context_objects,
                    "publication_read_calls": publication_reply.read_count,
                    "publication_unique_objects": publication_reply.unique_objects,
                    "supervised_exchanges": len(transport.timings),
                    "original_publishers_verified_without_writes": True,
                    "publication_context_ref": publication_material.context_ref.model_dump(
                        mode="json"
                    ),
                    "publication_is_proposed_current_summary_only": True,
                    "actual_source_qualification_granted": False,
                    "fixed_child_reaped": True,
                    "original_source_owner": receipt.scope.owner.model_dump(
                        mode="json"
                    ),
                    "actual_review_owner": owner.model_dump(mode="json"),
                    "source_retagged": False,
                    "task_claim_created": False,
                    "model_calls": 0,
                    "site_instances": 0,
                    "paid_calls": 0,
                    "old_receipts_modified": False,
                    "session_unchanged_by_proof": True,
                },
                indent=2,
            )
            + "\n"
        )


def test_fixed_whole_graph_returns_actual_context_inputs_without_leaf_exchanges(
    tmp_path: Path,
    installed_sources: InstalledFixture,
) -> None:
    from lab_generate_skill.domain.public_context import assemble_public_context

    case = actual_read_case(tmp_path, installed_sources)
    receipt = case.transport.read(
        case.material, case.controls.bind(case.op), context_inputs=True
    )
    reply = case.transport.last_reply
    assert reply is not None and reply.context_inputs is not None
    assert assemble_public_context(reply.context_inputs, receipt.operation) == receipt
    assert (
        reply.context_inputs.context_ref,
        reply.context_inputs.baseline_ref,
        reply.context_inputs.reset_ref,
    ) == (receipt.public_context_ref, receipt.baseline_ref, receipt.reset_ref)
    assert len(case.transport.timings) == 1
    case.current.admission.stop_new_io()
    with pytest.raises(InvalidTransition):
        case.transport.read(
            case.material, case.controls.bind(case.op), context_inputs=True
        )
    assert len(case.transport.timings) == 1

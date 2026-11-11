"""Original four Group contracts on isolated synthetic source/candidate domains.

Physical services/browser/permissions are explicit unit doubles. Production
record producers, full snapshots, native codecs and readonly comparison execute.
No old source is reowned, no live qualification or Actor permission is emitted.
"""

from pathlib import Path
from typing import Any, cast
import hashlib
import pytest
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.public_context import PublicContextInputs
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    OwnershipConflict,
    OperationStopped,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.sites.gitlab.tasks.group_equivalence import (
    GroupInitialComparison,
)
from lab_generate_skill.sites.gitlab.tasks.group_reads import GroupStateReads
from lab_generate_skill.sites.gitlab.tasks.group_recovery import GroupRecoverySnapshot
from gitlab_group_source_fixtures import group_source_unit_case
from test_gitlab_group_source_composition import contracts_for
from test_gitlab_group_complete_starts import PINS, W
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


class PairEvidence:
    def __init__(self, original: EvidenceReader, candidate: EvidenceReader) -> None:
        self.original, self.candidate = original, candidate

    def read(self, ref: EvidenceRef, control: OperationControl) -> bytes:
        try:
            return self.original.read(ref, control)
        except EvidenceNotFound:
            return self.candidate.read(ref, control)


def pair(tmp_path: Path, node_path: Path, source: str) -> tuple[Any, Any]:
    import gitlab_group_fixtures as inputs

    cases = []
    for attempt in ("original", "candidate"):
        root = tmp_path / attempt
        root.mkdir()
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(
                inputs,
                "FIXTURE",
                W
                / "experiments/sft-ordinary-source-bindings-v1/prepared/contracts"
                / (source + ".json"),
            )
            cases.append(
                group_source_unit_case(
                    root,
                    node_path / attempt,
                    patch,
                    contracts_for(source),
                    "none",
                    attempt_id=attempt,
                )
            )
    return cases[0], cases[1]


def source_inputs(c: Any) -> PublicContextInputs:
    f, receipt = c.facts, c.qualified.receipt
    public = PublicConstructionContext.model_validate_json(
        c.site.evidence.read(receipt.public_context_ref, guard())
    )
    return PublicContextInputs(
        context=public,
        context_ref=receipt.public_context_ref,
        baseline_inputs=f.baseline_inputs,
        baseline=f.baseline,
        baseline_ref=receipt.baseline_ref,
        reset_inputs=f.reset_inputs,
        reset=f.reset,
        reset_ref=receipt.reset_ref,
    )


@pytest.mark.parametrize("source", tuple(PINS))
def test_complete_Group_distinct_attempt_equivalence_and_refusals(
    tmp_path: Path,
    node_path: Path,
    source: str,
) -> None:
    left, right = pair(tmp_path, node_path, source)
    original, candidate = source_inputs(left), right.facts.baseline_inputs
    rule = GroupInitialComparison(
        GroupStateReads(
            PairEvidence(left.site.evidence, right.site.evidence), load_group_capture
        )
    )
    assert original.baseline.scope.owner == candidate.prepared.scope.owner
    assert original.baseline.scope.attempt_id != candidate.prepared.scope.attempt_id
    assert (
        original.baseline_inputs.environment.measured_state_sha256
        != candidate.environment.measured_state_sha256
    )
    saved = original.model_dump_json(), candidate.model_dump_json()
    for _ in range(2):
        assert rule.compare(original, candidate, guard(120)).status == "pass"
    assert saved == (original.model_dump_json(), candidate.model_dump_json())
    for fault in (
        "same_attempt",
        "owner",
        "public",
        "sequence",
        "url",
        "unready",
        "selection_missing",
        "snapshot_identity",
        "reset",
    ):
        src, current = original, candidate
        if fault == "same_attempt":
            current = original.baseline_inputs
        elif fault == "owner":
            scope = current.prepared.scope
            current = current.model_copy(
                update={
                    "prepared": current.prepared.model_copy(
                        update={
                            "scope": scope.model_copy(
                                update={
                                    "owner": scope.owner.model_copy(
                                        update={"job_id": "foreign"}
                                    )
                                }
                            )
                        }
                    )
                }
            )
        elif fault == "public":
            current = current.model_copy(
                update={
                    "public_task": current.public_task.model_copy(
                        update={"goal": "foreign goal"}
                    )
                }
            )
        elif fault == "sequence":
            current = current.model_copy(
                update={
                    "observation": current.observation.model_copy(
                        update={"sequence": 1}
                    )
                }
            )
        elif fault == "url":
            current = current.model_copy(
                update={
                    "observation": current.observation.model_copy(
                        update={
                            "tabs": (
                                current.observation.tabs[0].model_copy(
                                    update={
                                        "url": current.public_task.start_url + "wrong"
                                    }
                                ),
                            )
                        }
                    )
                }
            )
        elif fault in ("unready", "selection_missing"):
            checked = current.environment.checks
            checked = checked.model_copy(
                update={
                    "checks": tuple(
                        c.model_copy(
                            update=cast(
                                dict[str, object],
                                (
                                    {"status": "unknown"}
                                    if fault == "unready"
                                    else {"evidence": ()}
                                ),
                            )
                        )
                        for c in checked.checks
                    )
                }
            )
            current = current.model_copy(
                update={
                    "environment": current.environment.model_copy(
                        update={"checks": checked}
                    )
                }
            )
        elif fault == "snapshot_identity":
            current = current.model_copy(
                update={
                    "environment": current.environment.model_copy(
                        update={"measured_state_sha256": "0" * 64}
                    )
                }
            )
        elif fault == "reset":
            src = src.model_copy(
                update={"reset": src.reset.model_copy(update={"status": "quarantined"})}
            )
        with pytest.raises((OwnershipConflict, ValueError)):
            rule.compare(src, current, guard(120))
    # Changed complete contents remain valid typed measurements, but fail equality.
    references = {
        ref
        for c in candidate.environment.checks.checks
        for ref in c.evidence
        if ref.content_schema == "environment-selection/1"
    }
    selection = EnvironmentSelection.model_validate_json(
        right.site.evidence.read(next(iter(references)), guard())
    )
    snapshot = GroupRecoverySnapshot.model_validate_json(
        right.site.evidence.read(selection.snapshot_ref, guard())
    )
    snapshot = snapshot.model_copy(
        update={
            "state": snapshot.state.model_copy(
                update={
                    "inventory": snapshot.state.inventory.model_copy(
                        update={"sha256": "0" * 64}
                    )
                }
            )
        }
    )
    selection_ref = put(
        right.site.evidence,
        selection.model_copy(
            update={"snapshot_ref": put(right.site.evidence, snapshot)}
        ),
    )
    checked = candidate.environment.checks.model_copy(
        update={
            "checks": tuple(
                c.model_copy(update={"evidence": (selection_ref,)})
                for c in candidate.environment.checks.checks
            )
        }
    )
    measured = hashlib.sha256(
        snapshot.state.model_dump_json().encode()
        + snapshot.native_before.payload_ref.sha256.encode()
    ).hexdigest()
    changed = candidate.model_copy(
        update={
            "environment": candidate.environment.model_copy(
                update={"checks": checked, "measured_state_sha256": measured}
            )
        }
    )
    assert rule.compare(original, changed, guard(120)).status == "fail"
    control = guard(120)

    def cancelled() -> float:
        raise OperationStopped("CANCELLED", "unit-group-comparison")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(control, "checkpoint", cancelled)
        with pytest.raises(OperationStopped):
            rule.compare(original, candidate, control)


@pytest.mark.parametrize("value", [None, "", 0, {}, []])
def test_Group_equivalence_missing_or_wrong_reader_refuses_before_effects(
    value: Any,
) -> None:
    with pytest.raises(TypeError):
        GroupInitialComparison(value)

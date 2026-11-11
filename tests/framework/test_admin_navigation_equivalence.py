"""Same-owner original source/independent actual contents, including refusal cases."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.sites.shopping_admin.tasks.navigation_equivalence import (
    NavigationInitialComparison,
)
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationRecoverySnapshot,
)
from admin_navigation_equivalence_fixtures import baseline, source
from evidence_control_fixtures import EvidenceFixtureStore
from preparation_record_fixtures import put
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard


def test_distinct_instances_have_different_snapshot_identity_and_equal_actual_contents(
    tmp_path: Path, contracts: Any
) -> None:
    (tmp_path / "cas").mkdir()
    store = EvidenceFixtureStore(tmp_path / "cas")
    original = source(baseline(tmp_path / "source", store, contracts), store)
    candidate = baseline(tmp_path / "candidate", store, contracts, candidate=True)
    assert (
        original.baseline_inputs.environment.measured_state_sha256
        != candidate.environment.measured_state_sha256
    )
    rule = NavigationInitialComparison(store)
    saved = original.model_dump_json()
    assert rule.compare(original, candidate, guard()).status == "pass"
    assert (
        rule.compare(original, candidate, guard()).status == "pass"
    )  # Read-only replay, no native action.
    assert original.model_dump_json() == saved


@pytest.mark.parametrize(
    "fault",
    [
        "same_attempt",
        "owner",
        "task",
        "public",
        "sequence",
        "url",
        "environment",
        "initial",
        "reset",
        "selection_missing",
        "snapshot_identity",
        "legacy_no_contents",
        "content_changed",
    ],
)
def test_foreign_unready_or_unmeasured_state_is_never_equivalent(
    tmp_path: Path, contracts: Any, fault: str
) -> None:
    (tmp_path / "cas").mkdir()
    store = EvidenceFixtureStore(tmp_path / "cas")
    original = source(baseline(tmp_path / "source", store, contracts), store)
    candidate = baseline(tmp_path / "candidate", store, contracts, candidate=True)
    if fault == "same_attempt":
        candidate = original.baseline_inputs
    elif fault in ("owner", "task"):
        scope = candidate.prepared.scope
        scope = (
            scope.model_copy(
                update={"owner": scope.owner.model_copy(update={"job_id": "foreign"})}
            )
            if fault == "owner"
            else scope.model_copy(
                update={
                    "task": scope.task.model_copy(update={"source_task_id": "foreign"})
                }
            )
        )
        candidate = candidate.model_copy(
            update={"prepared": candidate.prepared.model_copy(update={"scope": scope})}
        )
    elif fault == "public":
        candidate = candidate.model_copy(
            update={
                "public_task": candidate.public_task.model_copy(
                    update={"goal": "different"}
                )
            }
        )
    elif fault in ("sequence", "url"):
        observed = (
            candidate.observation.model_copy(update={"sequence": 1})
            if fault == "sequence"
            else candidate.observation.model_copy(
                update={
                    "tabs": (
                        candidate.observation.tabs[0].model_copy(
                            update={"url": "http://127.0.0.1:12345/other"}
                        ),
                    )
                }
            )
        )
        candidate = candidate.model_copy(update={"observation": observed})
    elif fault in ("environment", "initial", "selection_missing"):
        key = "environment" if fault == "selection_missing" else fault
        record = getattr(candidate, key)
        checked = record.checks.model_copy(
            update={
                "checks": tuple(
                    (
                        c.model_copy(update={"evidence": ()})
                        if fault == "selection_missing"
                        else c.model_copy(update={"status": "unknown"})
                    )
                    for c in record.checks.checks
                )
            }
        )
        candidate = candidate.model_copy(
            update={key: record.model_copy(update={"checks": checked})}
        )
    elif fault == "reset":
        original = original.model_copy(
            update={
                "reset": original.reset.model_copy(update={"status": "quarantined"})
            }
        )
    elif fault == "snapshot_identity":
        candidate = candidate.model_copy(
            update={
                "environment": candidate.environment.model_copy(
                    update={"measured_state_sha256": "0" * 64}
                )
            }
        )
    else:
        refs = {
            r
            for c in candidate.environment.checks.checks
            for r in c.evidence
            if r.content_schema == "environment-selection/1"
        }
        selection = EnvironmentSelection.model_validate_json(
            store.read(next(iter(refs)))
        )
        saved = NavigationRecoverySnapshot.model_validate_json(
            store.read(selection.snapshot_ref)
        )
        assert saved.contents is not None
        contents = (
            None
            if fault == "legacy_no_contents"
            else saved.contents.model_copy(
                update={
                    "measured": saved.contents.measured.model_copy(
                        update={"search_documents_sha256": "0" * 64}
                    )
                }
            )
        )
        saved = saved.model_copy(update={"contents": contents})
        selection_ref = put(
            store, selection.model_copy(update={"snapshot_ref": put(store, saved)})
        )
        checked = candidate.environment.checks
        checked = checked.model_copy(
            update={
                "checks": tuple(
                    c.model_copy(update={"evidence": (selection_ref,)})
                    for c in checked.checks
                )
            }
        )
        candidate = candidate.model_copy(
            update={
                "environment": candidate.environment.model_copy(
                    update={"checks": checked}
                )
            }
        )
    if fault == "content_changed":
        assert (
            NavigationInitialComparison(store)
            .compare(original, candidate, guard())
            .status
            == "fail"
        )
    else:
        with pytest.raises((OwnershipConflict, ValueError)):
            NavigationInitialComparison(store).compare(original, candidate, guard())

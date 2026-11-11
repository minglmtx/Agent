"""Selected Map comparison boundaries and original non-equivalent Actor refusal."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.sites.task_initialization import (
    TaskInitializationUnconfirmed,
)
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted, OwnershipConflict
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
)
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.evaluation import CheckResult
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.navigation_equivalence import (
    NavigationInitialComparison,
)
from site_instance_fixtures import node_path as node_path
from task_initialization_port_fixtures import initialization_case


def test_native_fingerprint_mismatch_and_unready_views_cannot_compare_equal(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with initialization_case(node_path, monkeypatch) as case:
        case.start()
        init = case.initialization
        store = case.preparation.original.resource.evidence
        op = init.declaration.comparison_operation
        control = init.controls.bind(op)
        receipt = PublicContextReceipt.model_validate_json(
            store.read(init.declaration.source_context_receipt_ref)
        )
        source = init.contexts.facts.context(receipt, op, control)
        candidate = init.state.baseline_inputs
        assert candidate is not None
        rule = NavigationInitialComparison()
        changed = candidate.model_copy(
            update={
                "environment": candidate.environment.model_copy(
                    update={"measured_state_sha256": "f" * 64}
                )
            }
        )
        mismatch = rule.compare(source, changed, control)
        assert mismatch.status == "fail"
        assert mismatch.checks[0].reason_code == "ORIGINAL_COMPLETE_STATE_DIFFERS"
        variants = (
            candidate.model_copy(
                update={
                    "public_task": candidate.public_task.model_copy(
                        update={"start_url": "http://127.0.0.1:1/"}
                    )
                }
            ),
            candidate.model_copy(
                update={
                    "prepared": candidate.prepared.model_copy(
                        update={"scope": source.baseline.scope}
                    )
                }
            ),
            candidate.model_copy(
                update={
                    "observation": candidate.observation.model_copy(
                        update={"sequence": 1}
                    )
                }
            ),
            candidate.model_copy(
                update={
                    "observation": candidate.observation.model_copy(update={"tabs": ()})
                }
            ),
            candidate.model_copy(
                update={
                    "observation": candidate.observation.model_copy(
                        update={"last_action_error": "unit page not ready"}
                    )
                }
            ),
            candidate.model_copy(
                update={
                    "environment": candidate.environment.model_copy(
                        update={
                            "checks": StateChecks(
                                required=candidate.spec.environment_checks, checks=()
                            )
                        }
                    )
                }
            ),
        )
        for variant in variants:
            with pytest.raises(OwnershipConflict):
                rule.compare(source, variant, control)


@pytest.mark.parametrize(
    "status,expected", [("fail", "rejected"), ("unknown", "unknown")]
)
def test_non_equivalent_initial_state_is_saved_but_never_admitted_to_actor(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, status: str, expected: str
) -> None:
    with initialization_case(node_path, monkeypatch) as case:

        class Result:
            def compare(
                self,
                source: PublicContextInputs,
                candidate: BaselineInputs,
                control: OperationControl,
            ) -> StateChecks:
                control.checkpoint()
                return StateChecks(
                    required=candidate.spec.equivalence_checks,
                    checks=tuple(
                        CheckResult.model_validate(
                            dict(
                                name=n,
                                status=status,
                                reason_code="SYNTHETIC_COMPARISON_RESULT",
                                evidence=(
                                    candidate.environment_ref,
                                    source.baseline_ref,
                                ),
                            )
                        )
                        for n in candidate.spec.equivalence_checks
                    ),
                )

        case.initialization.comparison = Result()
        with pytest.raises(TaskInitializationUnconfirmed) as caught:
            case.start()
        state = case.initialization.state
        assert caught.value.failed_phase == "comparison"
        assert state.equivalence is not None and state.equivalence.status == expected
        assert state.equivalence_ref is not None and state.result is None
        assert case.browser.phase == "open"
        assert state.equivalence_ref in caught.value.references
        with pytest.raises(DispatchAlreadyCommitted):
            case.start()

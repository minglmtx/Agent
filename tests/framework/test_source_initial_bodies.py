"""Original source constructors, actual producer graph and bounded close; kernel/page are unit premises."""

from typing import Any
import pytest
from site_instance_fixtures import node_path as node_path
from lab_generate_skill.ports.lifecycle import OperationControl
from test_map_source_qualification import (
    source_case as source_case,
    test_source_initializer_unique_initial_observation_restore_reset_and_close_before_publication as original_case,
)


@pytest.mark.parametrize(
    "cancel_after_reset,lose_restore_return,wrong_body",
    [
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (False, False, True),
    ],
)
def test_original_source_complete_bodies_and_close(
    source_case: Any,
    monkeypatch: pytest.MonkeyPatch,
    cancel_after_reset: bool,
    lose_restore_return: bool,
    wrong_body: bool,
) -> None:
    class Current:
        calls = 0

        def check_current(self, control: OperationControl) -> None:
            control.checkpoint()
            self.calls += 1

    if wrong_body:
        from lab_generate_skill.adapters.browsergym.source_qualification_observation import (
            SourceQualificationObservationAuthority,
        )
        from lab_generate_skill.domain.errors import EvidenceIntegrityError

        verify = SourceQualificationObservationAuthority.verify

        def reject_changed_body(
            self: Any, inputs: Any, checks: Any, operation: Any, control: Any
        ) -> None:
            changed = inputs.model_copy(
                update={
                    "acquired": inputs.acquired.model_copy(
                        update={
                            "operation": inputs.acquired.operation.model_copy(
                                update={"operation_id": "wrong-acquired-body"}
                            )
                        }
                    )
                }
            )
            with pytest.raises(EvidenceIntegrityError):
                verify(self, changed, checks, operation, control)
            verify(self, inputs, checks, operation, control)

        monkeypatch.setattr(
            SourceQualificationObservationAuthority, "verify", reject_changed_body
        )
    current = Current()
    original_case(
        source_case,
        monkeypatch,
        cancel_after_reset,
        lose_restore_return,
        source_reads=current,
    )
    assert current.calls >= 4

"""Normal/valid-negative original initial/Actor/page terminal proof composition.

The shared Actor/journal/worker/wire/reader run with explicit model/page/kernel
doubles; this is not an original task execution or actual production permission or default full-capture acceptance.
"""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.admin_navigation_terminal import (
    read_admin_navigation_terminal,
)
from lab_generate_skill.evaluators.shopping_admin.navigation import (
    AdminNavigationEvaluator,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from admin_navigation_terminal_fixtures import terminal_case
from preparation_record_fixtures import put
from test_admin_navigation_input import contracts as contracts
from test_slurm_commands import guard


@pytest.mark.parametrize("negative", [False, True])
@pytest.mark.parametrize("current", [False, True], ids=["legacy1", "current2"])
def test_original_complete_terminal_proof_retains_valid_business_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    negative: bool,
    current: bool,
) -> None:
    with terminal_case(
        tmp_path, monkeypatch, contracts, negative=negative, current=current
    ) as c:
        loaded = read_admin_navigation_terminal(
            c.store, c.preparations, c.reference, c.contract, c.operation, guard(30)
        )
        original = c.selection.model_dump_json()
        result = AdminNavigationEvaluator(loaded.selected).evaluate(
            c.contract, c.store, guard(30)
        )
        assert result.status == ("failure" if negative else "success")
        assert result.reward == (0 if negative else 1)
        assert c.selection.model_dump_json() == original
        assert c.initial.returned.observation.sequence == 0
        assert loaded.returned.observation.sequence == 1
        assert c.snapshot.project().sealed is not None


def test_terminal_cannot_retarget_original_final_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> None:
    with terminal_case(tmp_path, monkeypatch, contracts) as c:
        selected = c.selection.model_copy(
            update={
                "terminal_return_ref": c.initial.acquired.details.started.initial_return_ref
            }
        )
        with pytest.raises(EvidenceIntegrityError, match="final return"):
            read_admin_navigation_terminal(
                c.store,
                c.preparations,
                put(c.store, selected),
                c.contract,
                c.operation,
                guard(30),
            )

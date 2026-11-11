"""Current capture closes the original browser before native guard and judgment.

Synthetic source/model/page/kernel grants are explicit. This checks the actual
shared capture producer and Admin immutable reader, not actual run eligibility.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from lab_generate_skill.sites.shopping_admin.tasks.navigation_recovery_contract import (
    NavigationRestored,
)
from admin_navigation_capture_fixtures import capture_case
from test_admin_navigation_input import contracts as contracts
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("negative", [False, True])
def test_original_actor2_browser_close_guard_and_readonly_navigation_judgment(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contracts: Any,
    negative: bool,
) -> None:
    with capture_case(
        tmp_path, node_path, monkeypatch, contracts, negative=negative
    ) as c:
        result = c.collect()
        q = c.qualified
        control = q["c"].controls.bind(c.plan.operation)
        assert result.contract == c.plan.evaluation
        assert c.capture.state.phase == "captured" and c.browser.phase == "closed"
        assert c.site_authority.calls == 1 and q["worker"].phase == "prepared"
        evaluated = c.evaluator.evaluate(c.plan.evaluation, q["store"], control)
        assert evaluated.status == ("failure" if negative else "success")
        assert evaluated.reward == (0 if negative else 1)
        with pytest.raises(DispatchAlreadyCommitted):
            c.collect()
        assert c.site_authority.calls == 1

        def no_write(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("Immutable navigation review must not write")

        with monkeypatch.context() as patch:
            patch.setattr(q["store"], "put", no_write)
            assert (
                c.evaluator.evaluate(c.plan.evaluation, q["store"], control)
                == evaluated
            )
        original = q["prepare"]
        restore = original.model_copy(
            update={
                "action": "restore",
                "operation": original.operation.cleanup(
                    "restore-after-capture", now=datetime.now(timezone.utc), seconds=30
                ),
            }
        )
        restored = q["worker"].execute_task(restore, control=control)
        assert (
            NavigationRestored.model_validate_json(restored.private_result).task
            == c.plan.evaluation.identity
        )

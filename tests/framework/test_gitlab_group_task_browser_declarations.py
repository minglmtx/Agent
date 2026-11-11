"""Late task codec on original native facts; common declaration owner is reused.

Native SQL/services/physical permissions remain explicit existing unit premises.
No actual browser/model or source/Actor qualification is produced.
"""

from typing import Any
import pytest

from lab_generate_skill.bootstrap.gitlab_group_task_browser_declarations import (
    prepared_group_browser_initialization,
)
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from gitlab_group_task_port_fixtures import GroupPortCase
from test_gitlab_group_task_ports import p as p
from site_instance_fixtures import node_path as node_path


def selected(p: GroupPortCase) -> tuple[Any, Any, Any, Any]:
    assert p.acquire() and p.prepare()
    state = p.preparation.state
    assert state.result is not None
    prepared = p.preparation.records.load(
        state.result.publication, p.declaration.prepare_operation
    )
    site = state.original_acquired().site_started_ref
    operation = p.operation("initial-declaration")
    return (
        prepared.public_task,
        state.result.publication.prepared_ref,
        site,
        p.resource.controls.bind(operation),
    )


def test_all4_current_accounts_original_start_and_repeated_codec(
    p: GroupPortCase,
) -> None:
    public, prepared, site, control = selected(p)
    first = prepared_group_browser_initialization(
        p.preparation, public, prepared, site, control
    )
    assert first.native_account_id == 1
    assert first.prepared_ref == prepared and first.site_ref == site
    first.check_task(public)
    assert first == prepared_group_browser_initialization(
        p.preparation, public, prepared, site, control
    )
    assert [r.action for r in p.requests] == ["snapshot", "prepare"]


def test_wrong_prepared_or_site_and_partial_prepare_never_declare(
    p: GroupPortCase,
) -> None:
    public, prepared, site, control = selected(p)
    for wrong_prepared, wrong_site in (
        (prepared.model_copy(update={"sha256": "0" * 64}), site),
        (prepared, site.model_copy(update={"sha256": "0" * 64})),
    ):
        with pytest.raises((ValueError, OwnershipConflict)):
            prepared_group_browser_initialization(
                p.preparation, public, wrong_prepared, wrong_site, control
            )
    state = p.preparation.state
    result = state.prepare_result
    try:
        state.prepare_result = None
        with pytest.raises(OwnershipConflict):
            prepared_group_browser_initialization(
                p.preparation, public, prepared, site, control
            )
        assert result is not None
        state.prepare_result = result.model_copy(update={"request_sha256": "0" * 64})
        with pytest.raises(OwnershipConflict):
            prepared_group_browser_initialization(
                p.preparation, public, prepared, site, control
            )
    finally:
        state.prepare_result = result
    assert [r.action for r in p.requests] == ["snapshot", "prepare"]


def test_cancelled_native_read_never_declares_or_dispatches(p: GroupPortCase) -> None:
    public, prepared, site, _ = selected(p)

    class Cancelled:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "group-browser-declaration")

        def wait(self, seconds: float) -> None:
            raise AssertionError("No wait is needed for declaration")

    with pytest.raises(OperationStopped):
        prepared_group_browser_initialization(
            p.preparation, public, prepared, site, Cancelled()
        )
    assert [r.action for r in p.requests] == ["snapshot", "prepare"]


@pytest.mark.parametrize("value", [None, "", {}, [], 0, True])
def test_untyped_preparation_refuses_before_reads(value: Any) -> None:
    with pytest.raises(TypeError):
        prepared_group_browser_initialization(value, value, value, value, value)

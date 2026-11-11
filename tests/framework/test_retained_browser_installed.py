"""Reuse current installed single-POST scenario with the new ownership handle.

The injected factory is local to this test, never a production authority or a
second worker. Native installation, request count, trace, complete-domain proof
and refusal assertions are the existing scenario's unchanged implementation.
"""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import DispatchAlreadyCommitted
from installed_source_fixtures import (
    installed_sources as installed_sources,
    InstalledFixture,
)
from worker_install_fixtures import installed_worker as installed_worker
import test_browser_resource_installed as scenario


@pytest.mark.parametrize("deny_closure", [False, True])
def test_installed_original_resource_through_retained_owner(
    installed_sources: InstalledFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    deny_closure: bool,
) -> None:
    handles: list[RetainedBrowserResource] = []

    def factory(
        spec: BrowserResourceSpec, operation: OperationContext, **kwargs: Any
    ) -> RetainedBrowserResource:
        handle = RetainedBrowserResource(spec, operation, **kwargs)
        handles.append(handle)
        return handle

    monkeypatch.setattr(scenario, "registered_browser", factory)
    scenario.test_installed_resource_trace_save_once_and_original_step_closure(
        installed_sources, tmp_path, monkeypatch, deny_closure
    )
    assert len(handles) == 2
    assert handles[1].spec == handles[0].spec
    assert handles[1].phase == "start-unconfirmed"
    assert isinstance(handles[1].open_error, DispatchAlreadyCommitted)
    assert handles[1].closed is None
    if deny_closure:
        assert handles[0].phase == "close-unconfirmed"
        assert handles[0].closed is None and handles[0].close_error is not None
    else:
        assert handles[0].phase == "closed"
        assert handles[0].closed is not None

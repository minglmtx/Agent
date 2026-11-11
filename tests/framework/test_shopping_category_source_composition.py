"""Source constructor through native, first capture, publication and cleanup."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.worker_client import BrowserWorkerFailure
from lab_generate_skill.bootstrap.shopping_category_source_qualification import (
    CategoryNavigationSourceUnconfirmed,
)
from lab_generate_skill.domain.errors import OperationStopped
from shopping_category_source_fixtures import source_unit_case
from test_shopping_category_navigation_input import originals as originals
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "fault", ["none", "capture", "cancel-after-reset", "restore-return-lost"]
)
def test_original_source_native_initial_capture_closed_publication_and_failure_cleanup(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    c = source_unit_case(tmp_path, node_path, monkeypatch, originals[0], fault)
    if fault == "none":
        result = c.run()
        assert len(c.publications) == 1 and result is c.publications[0]
        assert result.receipt.scope == c.owner.scope
        assert c.owner._sealed
        with pytest.raises(PermissionError):
            result.contexts.publish_context(result.receipt, c.site.op)
    else:
        with pytest.raises(CategoryNavigationSourceUnconfirmed) as caught:
            c.run()
        error = caught.value
        if isinstance(error.primary, BrowserWorkerFailure):
            print(error.primary.reply.model_dump_json())
        if error.primary is not None and not isinstance(
            error.primary, (PermissionError, OperationStopped)
        ):
            import traceback

            traceback.print_exception(error.primary)
        for secondary in error.cleanup_errors:
            if not isinstance(secondary, OSError):
                import traceback

                traceback.print_exception(secondary)
        assert not c.publications and not error.actual_actor_dispatched
        assert error.progress.restore_attempted
        if fault == "restore-return-lost":
            assert error.primary is None and error.progress.reset is None
            assert len(error.cleanup_errors) == 1 and isinstance(
                error.cleanup_errors[0], OSError
            )
        else:
            assert error.cleanup_errors == ()
            assert error.progress.reset is not None
            assert error.progress.reset.status == "safe"
            if fault == "capture":
                assert isinstance(error.primary, BrowserWorkerFailure)
                assert error.primary.reply.error is not None
                assert error.primary.reply.error.type_name == "PermissionError"
                assert error.primary.reply.phase == "capture"
            else:
                assert isinstance(error.primary, OperationStopped)
    read = c.site.op.cleanup("source-final-read", now=c.site.clock.utcnow(), seconds=30)
    assert c.site.journal.read(c.site.spec.token, read).state == "closed"
    assert len(c.site.channels) == 1 and len(c.browsers) == 1
    browser = c.browsers[0]
    browser_read = browser.op.cleanup(
        "source-browser-final-read", now=c.site.clock.utcnow(), seconds=30
    )
    assert browser.journal.read(browser.spec.token, browser_read).state == "closed"

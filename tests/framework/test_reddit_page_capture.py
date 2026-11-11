"""Exact current document/account facts, unsupported collectors and cancellation."""

from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.sites.reddit.page_capture import (
    RedditPageHealthCollector,
    PAGE_HEALTH_PROGRAM,
)
from lab_generate_skill.sites.reddit.evidence_schema import RedditPageHealth
from lab_generate_skill.domain.errors import OperationStopped
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "unavailable",
        "changed",
        "login",
        "bool_status",
        "string_status",
        "zero_status",
        "empty",
        "wrong_type",
        "title_too_large",
        "collector",
        "version",
        "native_error",
    ],
)
def test_only_current_native_document_and_account_are_returned(fault: str) -> None:
    calls: list[str] = []
    error = OSError("original document unavailable")
    url = "http://127.0.0.1:12001/submit"

    def evaluate(script: str) -> Any:
        calls.append(script)
        assert script == PAGE_HEALTH_PROGRAM
        if fault == "native_error":
            raise error
        if fault in ("empty", "wrong_type"):
            return {} if fault == "empty" else []
        return dict(
            schema_version="reddit-page-health/1",
            url=url,
            title="x" * 65537 if fault == "title_too_large" else "Submit · Reddit",
            http_status=(
                None
                if fault == "unavailable"
                else (
                    True
                    if fault == "bool_status"
                    else (
                        "200"
                        if fault == "string_status"
                        else 0 if fault == "zero_status" else 200
                    )
                )
            ),
            status_source=(
                "unavailable" if fault == "unavailable" else "navigation_timing"
            ),
            login_page=fault == "login",
            error_page=False,
        )

    page = SimpleNamespace(
        evaluate=evaluate, url=url + "changed" if fault == "changed" else url
    )
    collector = RedditPageHealthCollector()
    args = (
        page,
        "other" if fault == "collector" else "reddit-page-health",
        "0" if fault == "version" else "1",
        guard(),
    )
    if fault in ("none", "unavailable", "changed", "login"):
        result = RedditPageHealth.model_validate_json(collector.collect(*args))
        assert result.http_status == (
            None if fault in ("unavailable", "changed") else 200
        )
        assert result.status_source == (
            "document_changed"
            if fault == "changed"
            else "unavailable" if fault == "unavailable" else "navigation_timing"
        )
    else:
        with pytest.raises(
            OSError if fault == "native_error" else ValueError
        ) as caught:
            collector.collect(*args)
        if fault == "native_error":
            assert caught.value is error
    assert len(calls) == (0 if fault in ("collector", "version") else 1)


def test_cancelled_capture_never_uses_the_page() -> None:
    class Stopped:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "original-document")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(OperationStopped):
        RedditPageHealthCollector().collect(
            SimpleNamespace(
                evaluate=lambda p: pytest.fail("No read after cancellation")
            ),
            "reddit-page-health",
            "1",
            Stopped(),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("none", None),
        ("site", "map"),
        ("family", "other"),
        ("contract_version", 2),
        ("split", "test"),
    ],
)
def test_fixed_factory_dispatches_only_selected_original_contract(
    field: str, value: Any
) -> None:
    from lab_generate_skill.bootstrap.browser_capture import browser_collector
    from browser_worker_fixtures import configuration
    from test_reddit_image_inputs import public_task

    base = configuration()
    public = public_task()
    if field != "none":
        public = public.model_copy(
            update={"identity": public.identity.model_copy(update={field: value})}
        )
    spec = base.spec.model_copy(
        update={
            "task": public,
            "scope": base.spec.scope.model_copy(update={"task": public.identity}),
        }
    )
    collector = browser_collector(base.model_copy(update={"spec": spec}))
    assert (
        isinstance(collector, RedditPageHealthCollector)
        if field == "none"
        else collector is None
    )

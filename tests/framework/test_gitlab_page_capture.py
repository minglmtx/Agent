"""Exact current document/account facts, unsupported collectors and cancellation."""

from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.sites.gitlab.page_capture import (
    GitlabPageHealthCollector,
    GitlabPageHealth,
    PAGE_HEALTH_PROGRAM,
)
from lab_generate_skill.domain.errors import OperationStopped
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "unavailable",
        "changed",
        "login",
        "missing_account",
        "bool_status",
        "string_status",
        "zero_status",
        "bool_account",
        "string_account",
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
    url = "http://127.0.0.1:12001/-/profile/keys"

    def evaluate(script: str) -> Any:
        calls.append(script)
        assert script == PAGE_HEALTH_PROGRAM
        if fault == "native_error":
            raise error
        if fault in ("empty", "wrong_type"):
            return {} if fault == "empty" else []
        return dict(
            schema_version="gitlab-page-health/1",
            url=url,
            title="x" * 65537 if fault == "title_too_large" else "SSH Keys · GitLab",
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
            account_id=(
                None
                if fault in ("login", "missing_account")
                else (
                    True
                    if fault == "bool_account"
                    else "17" if fault == "string_account" else 17
                )
            ),
        )

    page = SimpleNamespace(
        evaluate=evaluate, url=url + "changed" if fault == "changed" else url
    )
    collector = GitlabPageHealthCollector()
    args = (
        page,
        "other" if fault == "collector" else "gitlab-page-health",
        "0" if fault == "version" else "1",
        guard(),
    )
    if fault in ("none", "unavailable", "changed", "login", "missing_account"):
        result = GitlabPageHealth.model_validate_json(collector.collect(*args))
        assert result.http_status == (
            None if fault in ("unavailable", "changed") else 200
        )
        assert result.account_id == (
            None if fault in ("changed", "login", "missing_account") else 17
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
        GitlabPageHealthCollector().collect(
            SimpleNamespace(
                evaluate=lambda p: pytest.fail("No read after cancellation")
            ),
            "gitlab-page-health",
            "1",
            Stopped(),
        )

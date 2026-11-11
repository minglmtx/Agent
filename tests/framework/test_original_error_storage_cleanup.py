"""Original registration/cleanup combination when primary failure outlives CAS."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.sites.resource import registered_site
from lab_generate_skill.domain.errors import OperationStopped
from browser_resource_fixtures import resource_case as browser_case
from site_resource_fixtures import resource_case as site_case


@pytest.mark.parametrize("role", ["browser", "site"])
@pytest.mark.parametrize("first", ["initialization", "preparation-timeout"])
def test_original_primary_and_store_failure_preserve_independent_physical_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str, first: str
) -> None:
    c: Any = (
        browser_case(tmp_path, monkeypatch)
        if role == "browser"
        else site_case(tmp_path, monkeypatch)
    )
    register: Any = registered_browser if role == "browser" else registered_site
    primary = (
        ValueError("Original initialization failed")
        if first == "initialization"
        else OperationStopped("DEADLINE_EXCEEDED", c.op.operation_id)
    )
    persistence = OSError("Original evidence store unavailable after primary")
    close_commands = []

    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise persistence

    with monkeypatch.context() as patch:
        with pytest.raises(BaseExceptionGroup) as failed:
            with register(
                c.spec,
                c.op,
                journal=c.journal,
                evidence=c.evidence,
                controls=c.controls,
                clock=c.clock,
                authority=c.authority,
                cleanup_seconds=120,
            ):
                channel = c.channels[0]
                exchange = channel.exchange

                def observe(raw: bytes, control: Any) -> bytes:
                    if json.loads(raw)["phase"] == "close":
                        close_commands.append(raw)
                        assert 0 < control.checkpoint() <= 10
                    result = exchange(raw, control)
                    assert type(result) is bytes
                    return result

                patch.setattr(channel, "exchange", observe)
                patch.setattr(c.evidence, "put", unavailable)
                patch.setattr(c.evidence, "read", unavailable)
                raise primary

    def leaves(error: BaseException) -> list[BaseException]:
        if isinstance(error, BaseExceptionGroup):
            return [leaf for e in error.exceptions for leaf in leaves(e)]
        return [error]

    errors = leaves(failed.value)
    assert errors[0] is primary and any(e is persistence for e in errors)
    assert len(c.channels) == 1 and len(close_commands) == 1
    assert c.channels[0].capture.termination.state == "reaped"
    # No storage success can be invented from the physical process exit.
    assert c.journal.read(c.spec.token, c.op).state == "acquired"

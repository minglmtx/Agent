"""Slow current ownership checks precede the short original-channel stop cap."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
import json
import pytest

from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.sites.resource import registered_site
from lab_generate_skill.adapters.processes import deadline
from lab_generate_skill.ports.lifecycle import OperationControl
from browser_resource_fixtures import resource_case as browser_case
from site_resource_fixtures import resource_case as site_case


@pytest.mark.parametrize("role", ["browser", "site"])
@pytest.mark.parametrize("fault", ["none", "primary", "authority"])
def test_slow_cleanup_authority_keeps_short_wire_stop_and_original_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str, fault: str
) -> None:
    c: Any = (
        browser_case(tmp_path, monkeypatch)
        if role == "browser"
        else site_case(tmp_path, monkeypatch)
    )
    register: Any = registered_browser if role == "browser" else registered_site
    elapsed = [0.0]
    monkeypatch.setattr(deadline, "time", SimpleNamespace(monotonic=lambda: elapsed[0]))
    original_verify = c.authority.verify
    seen: list[str] = []
    wire_controls: list[OperationControl] = []
    primary = ValueError("original initialization failed")

    def verify(*args: Any, **kwargs: Any) -> None:
        original_verify(*args, **kwargs)
        if args[1] == "close":
            control = args[-1]
            assert control.checkpoint() > 60
            assert (args[-2].deadline - c.clock.utcnow()).total_seconds() > 60
            seen.append("current-authority")
            elapsed[0] += 12
            control.checkpoint()
            if fault == "authority":
                raise PermissionError("current cleanup authority denied")

    monkeypatch.setattr(c.authority, "verify", verify)

    def body() -> None:
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
            original_exchange, original_finish = channel.exchange, channel.finish

            def exchange(payload: bytes, control: OperationControl) -> bytes:
                if json.loads(payload)["phase"] == "close":
                    assert seen == ["current-authority"]
                    assert 0 < control.checkpoint() <= 10
                    wire_controls.append(control)
                reply = original_exchange(payload, control)
                assert type(reply) is bytes
                return reply

            def finish(control: OperationControl) -> Any:
                assert wire_controls == [control]
                assert 0 < control.checkpoint() <= 10
                seen.append("physical-reaped")
                return original_finish(control)

            monkeypatch.setattr(channel, "exchange", exchange)
            monkeypatch.setattr(channel, "finish", finish)
            if fault == "primary":
                raise primary

    if fault == "primary":
        with pytest.raises(ValueError) as caught:
            body()
        assert caught.value is primary
    elif fault == "authority":
        with pytest.raises(BaseExceptionGroup) as grouped:
            body()
        assert any(isinstance(e, PermissionError) for e in grouped.value.exceptions)
    else:
        body()
    record = c.journal.read(c.spec.token, c.op)
    if fault == "authority":
        assert record.state == "quarantined" and wire_controls == []
        assert c.channels[0].aborts == 1
    else:
        assert record.state == "closed" and seen == [
            "current-authority",
            "physical-reaped",
        ]
    assert c.channels[0].capture.termination.state == "reaped"

"""Unconfirmed child and unknown original store never permit another proof."""

from dataclasses import replace
from pathlib import Path
import pytest
from closed_source_read_fixtures import actual_read_case
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadFailure,
)
from lab_generate_skill.adapters.processes.capture import CommandCapture, CommandFailure
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import InvalidTransition
from lab_generate_skill.ports.lifecycle import OperationControl
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)


def test_real_reaped_child_withheld_ending_is_quarantined_without_retry(
    tmp_path: Path, installed_sources: InstalledFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = actual_read_case(tmp_path, installed_sources)
    original = c.transport.runner.run
    calls = 0

    def run(
        argv: tuple[str, ...],
        control: OperationControl,
        *,
        stdin_bytes: bytes | None = None,
    ) -> CommandCapture:
        nonlocal calls
        calls += 1
        capture = original(argv, control, stdin_bytes=stdin_bytes)
        assert capture.termination is not None and capture.termination.state == "reaped"
        # Explicit software fault: the physical ending is known by this fixture,
        # but that proof is withheld from the production consumer.
        return replace(capture, termination=None)

    monkeypatch.setattr(c.transport.runner, "run", run)
    with pytest.raises(CommandFailure) as failed:
        c.transport.read(c.material, c.controls.bind(c.op))
    assert failed.value.reason_code == "PROCESS_CLEANUP_UNCONFIRMED"
    assert c.transport.quarantined and c.transport.last_capture == failed.value.capture
    with pytest.raises(ClosedSourceReadFailure):
        c.transport.read(c.material, c.controls.bind(c.op))
    assert calls == 1


def test_original_unknown_session_rejects_read_scope_and_cannot_reinitialize(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    c = actual_read_case(tmp_path, installed_sources, fresh_cas=True)
    list((tmp_path / "sessions").glob("*.evidence-session.json"))[0].unlink()
    with pytest.raises(BaseExceptionGroup):
        c.current.store.put(
            b"fresh fault marker only",
            EvidenceMetadata(
                media_type="text/plain",
                content_schema="fault-marker/1",
                visibility="private",
                producer="fault-check",
            ),
            c.controls.bind(c.op),
        )
    assert c.current.store.state == "quarantined"
    before = {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()}
    with pytest.raises(InvalidTransition):
        c.transport.read(c.material, c.controls.bind(c.op))
    with pytest.raises(InvalidTransition):
        c.current.store.initialize(c.controls.bind(c.op))
    assert c.transport.last_capture is None
    assert {p.name: p.read_bytes() for p in (tmp_path / "sessions").iterdir()} == before

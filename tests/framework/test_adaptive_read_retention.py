"""Actual native reply and public read persistence after execution deadline."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.models.actor_count_protocol import (
    ActorCountCommand,
    decode_worker_command,
)
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.observation_read import (
    ReadObservationRegions,
    ObservationRegionRange,
)
from lab_generate_skill.domain.observation_read_return import ObservationReadUnconfirmed
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_context_fixtures import counter_case
from observation_read_fixtures import indexed
from state_contract_fixtures import op
from test_snapshot_observation_reads import reader_case


class ExpiringControl:
    expired = False

    def checkpoint(self) -> float:
        if self.expired:
            raise OperationStopped("DEADLINE_EXCEEDED", "original-read-execution")
        return 60.0

    def wait(self, seconds: float) -> None:
        self.checkpoint()


def test_native_count_return_is_saved_with_cleanup_control_without_recount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = counter_case(tmp_path)
    execution = ExpiringControl()
    original = c.channel.exchange

    def late(payload: bytes, control: OperationControl) -> bytes:
        raw = original(payload, control)
        if isinstance(decode_worker_command(payload), ActorCountCommand):
            execution.expired = True
        return raw

    monkeypatch.setattr(c.channel, "exchange", late)
    returned = c.counter.measure_with_return(
        c.input_ref, c.profile, c.policy, control=execution, retention_control=c.control
    )
    assert execution.expired and c.evidence.read(returned.evidence_ref, c.control)
    assert (
        sum(
            isinstance(decode_worker_command(p), ActorCountCommand)
            for p in c.channel.sent
        )
        == 1
    )
    assert c.channel.aborts == 0


def test_read_body_is_persisted_before_expired_execution_can_activate_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = indexed("[1] RootWebArea\n\t[2] button A\n")
    reads, progress, c, gate, session = reader_case(tmp_path, index)
    execution = ExpiringControl()
    original = c.channel.exchange

    def late(payload: bytes, control: OperationControl) -> bytes:
        raw = original(payload, control)
        if isinstance(decode_worker_command(payload), ActorCountCommand):
            execution.expired = True
        return raw

    monkeypatch.setattr(c.channel, "exchange", late)
    request = ReadObservationRegions(
        request_id="late-original-read",
        snapshot=index.snapshot,
        output_tokens=1000,
        ranges=(ObservationRegionRange(region_id="ax-line-1", unit="whole_region"),),
    )
    with pytest.raises(ObservationReadUnconfirmed) as caught:
        reads.read(
            request,
            op("late-read"),
            progress=progress,
            control=execution,
            retention_control=c.control,
        )
    known = caught.value
    assert isinstance(known.primary, OperationStopped) and known.result_ref is not None
    assert (
        c.evidence.read(known.result_ref, c.control)
        == known.payload.model_dump_json().encode()
    )
    assert c.evidence.read(known.count.evidence_ref, c.control)
    assert reads.active_return is None and len(session.body_calls) == 1
    with pytest.raises(OwnershipConflict):
        reads.read(
            request,
            op("forbidden-retry"),
            progress=progress,
            control=c.control,
            retention_control=c.control,
        )
    assert len(session.body_calls) == 1

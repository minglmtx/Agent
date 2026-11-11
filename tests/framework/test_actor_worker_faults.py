"""Unknown returns and final cancellation retain original effects without replay."""

import io
from pathlib import Path
import pytest
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.adapters.models.actor_worker_protocol import (
    decode_command,
    MAX_WORKER_PACKET,
)
from lab_generate_skill.adapters.models.actor_worker_stream import serve
from lab_generate_skill.adapters.processes.framing import frame
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_worker_fixtures import worker_case
from test_actor_worker import commands
from test_slurm_commands import guard


def test_lost_return_after_inference_never_resends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, loader, request, params, control, _, channel, client = worker_case(tmp_path)
    client.configure(control)
    original = channel.exchange
    unknown = OSError("reply acknowledgement lost")

    def exchange(raw: bytes, supplied: OperationControl) -> bytes:
        original(raw, supplied)
        raise unknown

    monkeypatch.setattr(channel, "exchange", exchange)
    with pytest.raises(OSError) as caught:
        client.generate(request, params, control)
    assert (
        caught.value is unknown
        and loader.session.calls == 1
        and loader.session.closed == 1
    )
    with pytest.raises(OwnershipConflict):
        client.generate(request, params, control)
    assert sum(decode_command(raw).operation == "generate" for raw in channel.sent) == 1


def test_final_cancel_keeps_decoded_actual_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, loader, request, params, control, _, channel, client = worker_case(tmp_path)
    client.configure(control)
    original = channel.exchange

    class StopAfterReturn:
        stopped = False

        def checkpoint(self) -> float:
            if self.stopped:
                raise OperationStopped("CANCELLED", "actual-return")
            return 10.0

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    stopped = StopAfterReturn()

    def exchange(raw: bytes, supplied: OperationControl) -> bytes:
        result = original(raw, supplied)
        stopped.stopped = True
        return result

    monkeypatch.setattr(channel, "exchange", exchange)
    with pytest.raises(OperationStopped) as caught:
        client.generate(request, params, stopped)
    assert getattr(caught.value, "actor_worker_reply").output == loader.session.output
    assert loader.session.calls == 1 and loader.session.closed == 1
    with pytest.raises(OwnershipConflict):
        client.generate(request, params, guard())


def test_framed_stream_retains_primary_and_release_failure(tmp_path: Path) -> None:
    configure, generate, _, loader, service = commands(tmp_path)
    cleanup = OSError("close failed")
    loader.session.cleanup_failure = cleanup
    payload = (
        b"".join(
            frame(c.model_dump_json().encode(), MAX_WORKER_PACKET)
            for c in (configure, generate)
        )
        + b"\0"
    )
    with pytest.raises(BaseExceptionGroup) as caught:
        serve(service, io.BytesIO(payload), io.BytesIO())
    assert (
        isinstance(caught.value.exceptions[0], EOFError)
        and caught.value.exceptions[1] is cleanup
    )
    assert loader.session.calls == loader.session.closed == 1

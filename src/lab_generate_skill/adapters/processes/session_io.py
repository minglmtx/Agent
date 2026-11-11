"""Nonblocking framed pipe exchange and bounded cumulative stderr draining.

No process ownership, restart or semantic model decoding. Caller serializes
access and must terminate the worker after any incomplete exchange.
"""

import os
import selectors
import subprocess
from lab_generate_skill.ports.lifecycle import OperationControl
from .framing import frame_size


def drain_error(fd: int, stderr: bytearray, limit: int) -> bool:
    chunk = os.read(fd, min(65536, limit + 1 - len(stderr)))
    stderr.extend(chunk)
    if len(stderr) > limit:
        raise ValueError("Worker stderr exceeds session budget")
    return bool(chunk)


def exchange(
    process: subprocess.Popen[bytes],
    packet: bytes,
    reply: bytearray,
    stderr: bytearray,
    limit: int,
    stderr_limit: int,
    control: OperationControl,
) -> bytes:
    assert (
        process.stdin is not None
        and process.stdout is not None
        and process.stderr is not None
    )
    sent = 0
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdin, selectors.EVENT_WRITE, "write")
        selector.register(process.stdout, selectors.EVENT_READ, "read")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        while True:
            remaining = control.checkpoint()
            for key, _ in selector.select(min(remaining, 0.05)):
                control.checkpoint()
                if key.data == "write":
                    try:
                        count = os.write(key.fd, packet[sent : sent + 65536])
                    except BlockingIOError:
                        continue
                    if count <= 0:
                        raise BrokenPipeError("Worker accepted no request bytes")
                    sent += count
                    if sent == len(packet):
                        selector.unregister(key.fileobj)
                elif key.data == "stderr":
                    try:
                        more = drain_error(key.fd, stderr, stderr_limit)
                    except BlockingIOError:
                        continue
                    if not more:
                        selector.unregister(key.fileobj)
                else:
                    try:
                        chunk = os.read(key.fd, min(65536, limit + 5 - len(reply)))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        raise EOFError(
                            "Worker closed response pipe before a complete frame"
                        )
                    reply.extend(chunk)
                    total = frame_size(reply, limit)
                    if total is not None and len(reply) == total:
                        if sent != len(packet):
                            raise ValueError(
                                "Worker replied before receiving full request"
                            )
                        control.checkpoint()
                        return bytes(reply[4:])


def wait_exit(
    process: subprocess.Popen[bytes],
    stderr: bytearray,
    stderr_limit: int,
    control: OperationControl,
) -> None:
    assert process.stdout is not None and process.stderr is not None
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ, "read")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        while selector.get_map() or process.poll() is None:
            remaining = control.checkpoint()
            for key, _ in selector.select(min(remaining, 0.05)):
                if key.data == "stderr":
                    try:
                        more = drain_error(key.fd, stderr, stderr_limit)
                    except BlockingIOError:
                        continue
                    if not more:
                        selector.unregister(key.fileobj)
                else:
                    try:
                        raw = os.read(key.fd, 1)
                    except BlockingIOError:
                        continue
                    if raw:
                        raise ValueError("Worker emitted output outside an exchange")
                    selector.unregister(key.fileobj)
            if not selector.get_map() and process.poll() is None:
                control.wait(min(0.02, remaining))
        control.checkpoint()
        if process.returncode != 0:
            raise ChildProcessError("Worker did not exit successfully")


def drain_pending_error(
    process: subprocess.Popen[bytes], stderr: bytearray, limit: int
) -> None:
    """Retain available diagnostics before cleanup closes the pipes."""
    if process.stderr is None or process.stderr.closed or len(stderr) > limit:
        return
    while True:
        try:
            if not drain_error(process.stderr.fileno(), stderr, limit):
                return
        except BlockingIOError:
            return

"""Write/sync/publication/cleanup faults retain actual trace facts and identities."""

import os
from pathlib import Path
from typing import cast
import pytest
from lab_generate_skill.domain.errors import (
    DispatchAlreadyCommitted,
    JournalCapacityExceeded,
    OwnershipConflict,
)
from lab_generate_skill.domain.trace_events import GenerationObserved
from lab_generate_skill.domain.trace_journal import (
    TRACE_EVENT,
    TraceJournalCommitUnconfirmed,
)
from test_atomic_snapshot import flatten
from test_run_journal import command
from trace_journal_fixtures import fixture


@pytest.mark.parametrize(
    "fault",
    ["write", "fsync", "replace", "unlink_and_close", "after_publish", "lock_close"],
)
def test_observed_fact_retained_across_transaction_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    snapshot = journal.create(data.plan, command("create", attempt="attempt"))
    events = data.events()
    snapshot = journal.append(events[0], 0, events[0].operation)
    event = events[1]
    path = tmp_path / "journal" / journal.file.name
    before = path.read_bytes()
    write0, sync0, replace0, unlink0, close0 = (
        os.write,
        os.fsync,
        os.replace,
        os.unlink,
        os.close,
    )
    published = False

    def write(fd: int, raw: bytes) -> int:
        if fault == "write" and ".pending-snapshot-" in os.readlink(
            f"/proc/self/fd/{fd}"
        ):
            raise OSError("primary write")
        return write0(fd, raw)

    def sync(fd: int) -> None:
        target = os.readlink(f"/proc/self/fd/{fd}")
        if fault == "fsync" and ".pending-snapshot-" in target:
            raise OSError("primary fsync")
        sync0(fd)
        if (
            fault == "after_publish"
            and published
            and target == str(tmp_path / "journal")
        ):
            raise OSError("lost sync acknowledgement")

    def replace(
        src: str,
        dst: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal published
        if src.startswith(".pending-snapshot-") and fault in (
            "replace",
            "unlink_and_close",
        ):
            raise OSError("primary replace")
        replace0(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
        if src.startswith(".pending-snapshot-"):
            published = True

    def unlink(target: str, *, dir_fd: int | None = None) -> None:
        if target.startswith(".pending-snapshot-") and fault == "unlink_and_close":
            raise OSError("cleanup unlink")
        unlink0(target, dir_fd=dir_fd)

    def close(fd: int) -> None:
        target = os.readlink(f"/proc/self/fd/{fd}")
        close0(fd)
        if fault == "unlink_and_close" and ".pending-snapshot-" in target:
            raise OSError("cleanup close")
        if fault == "lock_close" and target.endswith(".trace.json.lock"):
            raise OSError("lock cleanup")

    with monkeypatch.context() as patch:
        for name, fn in [
            ("write", write),
            ("fsync", sync),
            ("replace", replace),
            ("unlink", unlink),
            ("close", close),
        ]:
            patch.setattr(os, name, fn)
        with pytest.raises(TraceJournalCommitUnconfirmed) as caught:
            journal.append(event, 1, event.operation)
    assert TRACE_EVENT.validate_json(data.store.read(caught.value.event_ref)) == event
    assert caught.value.__cause__ is not None
    causes = [str(e) for e in flatten(caught.value.__cause__)]
    if fault == "unlink_and_close":
        assert causes == ["primary replace", "cleanup unlink", "cleanup close"]
    else:
        assert len(causes) == 1
    current = data.journal().read(command())
    if fault in ("after_publish", "lock_close"):
        assert current.revision == 2
    else:
        assert current == snapshot and path.read_bytes() == before
    fixed = data.journal().append(event, 1, event.operation)
    assert fixed.revision == 2 and fixed.events.count(event) == 1


def test_intent_acknowledgement_loss_does_not_grant_another_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = fixture(tmp_path)
    journal = data.journal()
    journal.create(data.plan, command("create", attempt="attempt"))
    event = data.events()[0]
    original = os.replace

    def replace(
        src: str,
        dst: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        original(src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
        if src.startswith(".pending-snapshot-"):
            raise OSError("lost intent acknowledgement")

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", replace)
        with pytest.raises(OSError):
            journal.append(event, 0, event.operation)
    current = data.journal().read(command())
    assert current.revision == 1 and current.project().intent is not None
    with pytest.raises(DispatchAlreadyCommitted):
        data.journal().append(event, 0, event.operation)


def test_unexpected_result_size_retains_original_fact_and_old_snapshot(
    tmp_path: Path,
) -> None:
    data = fixture(tmp_path)
    events = data.events()
    limit = len(events[0].model_dump_json().encode()) + 1
    event = cast(GenerationObserved, events[1])
    assert len(event.model_dump_json().encode()) > limit
    data.plan = data.plan.model_copy(
        update={
            "capacity": data.plan.capacity.model_copy(update={"max_event_bytes": limit})
        }
    )
    journal = data.journal()
    snapshot = journal.create(data.plan, command("create", attempt="attempt"))
    snapshot = journal.append(events[0], 0, events[0].operation)
    with pytest.raises(TraceJournalCommitUnconfirmed) as caught:
        journal.append(event, 1, event.operation)
    assert isinstance(caught.value.__cause__, JournalCapacityExceeded)
    assert TRACE_EVENT.validate_json(data.store.read(caught.value.event_ref)) == event
    assert journal.read(command()) == snapshot
    data.plan = data.plan.model_copy(
        update={
            "capacity": data.plan.capacity.model_copy(update={"max_event_bytes": 32768})
        }
    )
    with pytest.raises(OwnershipConflict):
        data.journal().read(command())

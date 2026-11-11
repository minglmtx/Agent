"""Real reader/count adapters; synthetic native tokens, no website/action replay."""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from lab_generate_skill.adapters.plans.observation_reads import SnapshotObservationReads
from lab_generate_skill.adapters.models.observation_body_counts import (
    ActorObservationBodyCounts,
)
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.observation_read import (
    ListObservationRegions,
    ReadObservationRegions,
    SearchObservationRegions,
    ObservationRegionRange,
    PublicObservationSnapshot,
)
from lab_generate_skill.domain.observation_read_progress import ObservationReadProgress
from lab_generate_skill.domain.observation_read_return import (
    ObservationReadCapacityBlocked,
    ObservationReadUnconfirmed,
)
from lab_generate_skill.policies.observation_index import ObservationIndex
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_context_fixtures import CounterCase, counter_case
from adaptive_observation_fixtures import ObservationSession
from observation_read_fixtures import indexed
from state_contract_fixtures import op


class CharacterSession(ObservationSession):
    def tokenize_observation(self, text: str) -> tuple[int, ...]:
        self.body_calls.append(text)
        return (7,) * ((len(text) + 3) // 4)


class CurrentGate:
    def __init__(self, snapshot: PublicObservationSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0
        self.revoked = False

    def require_current(
        self,
        snapshot: PublicObservationSnapshot,
        operation: OperationContext,
        *,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        self.calls += 1
        if self.revoked or snapshot != self.snapshot:
            raise OwnershipConflict("Original current read gate revoked")


def reader_case(tmp_path: Path, index: ObservationIndex) -> tuple[
    SnapshotObservationReads,
    ObservationReadProgress,
    CounterCase,
    CurrentGate,
    CharacterSession,
]:
    case = counter_case(tmp_path)
    session = CharacterSession()
    case.loader.session = session
    gate = CurrentGate(index.snapshot)
    counts = ActorObservationBodyCounts(
        case.counter, case.evidence, case.profile, case.policy, index.policy
    )
    reads = SnapshotObservationReads(index, case.evidence, gate, counts)
    progress = ObservationReadProgress(
        snapshot=index.snapshot, policy=index.policy, records=(), no_progress=0
    )
    return reads, progress, case, gate, session


def test_read_adapter_passes_original_body_without_reread_and_duplicate_recounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = indexed("[1] RootWebArea\n\t[2] button A\n\t[3] button B\n")
    reads, progress, case, gate, session = reader_case(tmp_path, index)
    original = case.evidence.read

    def no_source_read(
        reference: EvidenceRef, control: OperationControl | None = None
    ) -> bytes:
        assert (
            reference != index.snapshot.observation_ref
        ), "Already checked source was physically read again"
        return original(reference, control)

    monkeypatch.setattr(case.evidence, "read", no_source_read)
    a = ReadObservationRegions(
        request_id="a",
        snapshot=index.snapshot,
        output_tokens=1000,
        ranges=(ObservationRegionRange(region_id="ax-line-1", unit="whole_region"),),
    )
    returned = reads.read(a, op("read-a"), progress=progress, control=case.control)
    assert "[2] button A" in returned.body and "[3] button B" not in returned.body
    progress = progress.returned(returned.record)
    count_calls = len(session.body_calls)
    duplicate = reads.read(
        a.model_copy(update={"request_id": "a-repeat"}),
        op("repeat-a"),
        progress=progress,
        control=case.control,
    )
    progress = progress.returned(duplicate.record)
    assert len(session.body_calls) == count_calls and progress.no_progress == 1
    assert (
        duplicate.body == returned.body and duplicate.result_ref != returned.result_ref
    )
    b = a.model_copy(
        update={
            "request_id": "b",
            "ranges": (
                ObservationRegionRange(region_id="ax-line-2", unit="whole_region"),
            ),
        }
    )
    second = reads.read(b, op("read-b"), progress=progress, control=case.control)
    progress = progress.returned(second.record)
    restored = reads.read(
        a.model_copy(update={"request_id": "a-restored"}),
        op("restore-a"),
        progress=progress,
        control=case.control,
    )
    assert restored.body == returned.body and len(session.body_calls) == count_calls + 2
    progress = progress.returned(restored.record)
    assert (
        progress.remaining == 2
        and progress.warn_remaining
        and progress.no_progress == 0
    )
    assert case.loader.loads == 1 and session.calls == 0 and gate.calls >= 12
    reads.close()
    with pytest.raises(OwnershipConflict):
        reads.read(
            b.model_copy(update={"request_id": "closed"}),
            op("closed"),
            progress=progress,
            control=case.control,
        )
    case.client.close(case.control)


def test_table_read_pages_keep_complete_rows_and_headers_in_every_page(
    tmp_path: Path,
) -> None:
    text = (
        "[1] RootWebArea\n\t[2] table\n\t\t[3] row\n\t\t\t[4] columnheader Name\n"
        + "".join(
            f"\t\t[{10+i*2}] row record-{i}\n\t\t\t[{11+i*2}] gridcell value-{i}\n"
            for i in range(8)
        )
    )
    index = indexed(text, page_units=3)
    reads, progress, case, _, session = reader_case(tmp_path, index)
    request = ReadObservationRegions(
        request_id="rows",
        snapshot=index.snapshot,
        output_tokens=1500,
        ranges=(
            ObservationRegionRange(
                region_id="ax-line-1", unit="data_rows", start=0, end=8
            ),
        ),
    )
    contents: list[str] = []
    for page in range(3):
        returned = reads.read(
            request, op(f"rows-{page}"), progress=progress, control=case.control
        )
        progress = progress.returned(returned.record)
        assert "[4] columnheader Name" in returned.body
        assert returned.count.measurement.observation_tokens is not None
        assert returned.count.measurement.observation_tokens <= 1500
        contents.extend(
            fragment.text
            for fragment in returned.payload.fragments
            if fragment.purpose == "content"
        )
        if page < 2:
            assert (
                not returned.payload.complete
                and returned.payload.continuation is not None
            )
            request = request.model_copy(
                update={
                    "request_id": f"next-{page}",
                    "continuation": returned.payload.continuation,
                }
            )
        else:
            assert returned.payload.complete and returned.payload.results_exhausted
    for i in range(8):
        assert sum(f"gridcell value-{i}\n" in content for content in contents) == 1
    assert session.calls == 0
    reads.close()
    case.client.close(case.control)


def test_search_context_and_opaque_cursor_bind_original_query_options_and_scope(
    tmp_path: Path,
) -> None:
    index = indexed(
        "[1] RootWebArea\n"
        + "".join(f"\t[{i+2}] button Literal-{i}\n" for i in range(8)),
        search_hits=2,
    )
    reads, progress, case, gate, session = reader_case(tmp_path, index)
    request = SearchObservationRegions(
        request_id="search",
        snapshot=index.snapshot,
        output_tokens=1500,
        query="LITERAL-",
        region_ids=(),
    )
    first = reads.read(request, op("search"), progress=progress, control=case.control)
    progress = progress.returned(first.record)
    assert (
        len(first.payload.matches) == 2
        and first.payload.search_coverage_complete is False
    )
    assert (
        not first.payload.results_exhausted and first.payload.continuation is not None
    )
    before = len(session.body_calls)
    for changes in (
        {"query": "different"},
        {"output_tokens": 1499},
        {"continuation": "read-tampered"},
    ):
        invalid = request.model_copy(
            update={"request_id": "tamper", "continuation": first.payload.continuation}
            | changes
        )
        with pytest.raises(OwnershipConflict):
            reads.read(invalid, op("tamper"), progress=progress, control=case.control)
    assert len(session.body_calls) == before
    continued = request.model_copy(
        update={"request_id": "continued", "continuation": first.payload.continuation}
    )
    second = reads.read(
        continued, op("continued"), progress=progress, control=case.control
    )
    assert {m.match_span for m in first.payload.matches}.isdisjoint(
        m.match_span for m in second.payload.matches
    )
    progress = progress.returned(second.record)
    gate.revoked = True
    with pytest.raises(OwnershipConflict):
        reads.read(
            request.model_copy(update={"request_id": "revoked"}),
            op("revoked"),
            progress=progress,
            control=case.control,
        )
    assert len(session.body_calls) == before + 1 and session.calls == 0
    reads.close()
    case.client.close(case.control)


def test_counted_read_repartitions_by_native_tokens_and_does_not_fill_soft_threshold(
    tmp_path: Path,
) -> None:
    index = indexed(
        "[1] RootWebArea\n"
        + "".join(f"\t[{i+2}] button Item-{i} {'x'*100}\n" for i in range(15)),
        directory_entries=16,
    )
    reads, progress, case, _, session = reader_case(tmp_path, index)
    request = ListObservationRegions(
        request_id="directory", snapshot=index.snapshot, output_tokens=400
    )
    returned = reads.read(
        request, op("directory"), progress=progress, control=case.control
    )
    assert len(session.body_calls) > 1 and len(returned.payload.directory) < 16
    assert (
        returned.count.measurement.observation_tokens is not None
        and returned.count.measurement.observation_tokens <= 400
    )
    assert returned.payload.continuation is not None and not returned.payload.complete
    assert session.calls == 0
    reads.close()
    case.client.close(case.control)


def test_oversized_necessary_row_context_is_explicit_capacity_block_not_truncation(
    tmp_path: Path,
) -> None:
    index = indexed(
        "[1] RootWebArea\n\t[2] table\n\t\t[3] row\n\t\t\t[4] columnheader Name\n\t\t[5] row\n\t\t\t[6] gridcell "
        + "longcell" * 2000
        + "\n"
    )
    reads, progress, case, _, session = reader_case(tmp_path, index)
    request = ReadObservationRegions(
        request_id="long",
        snapshot=index.snapshot,
        output_tokens=300,
        ranges=(
            ObservationRegionRange(
                region_id="ax-line-1", unit="data_rows", start=0, end=1
            ),
        ),
    )
    with pytest.raises(ObservationReadCapacityBlocked, match="no silent truncation"):
        reads.read(request, op("long"), progress=progress, control=case.control)
    assert progress.active is None and session.calls == 0
    with pytest.raises(OwnershipConflict):
        reads.read(
            request.model_copy(update={"request_id": "do-not-replay"}),
            op("replay"),
            progress=progress,
            control=case.control,
        )
    reads.close()
    case.client.close(case.control)


def test_result_publication_failure_keeps_original_return_and_count_without_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = indexed("[1] RootWebArea\n\t[2] button A\n")
    reads, progress, case, _, session = reader_case(tmp_path, index)
    original = case.evidence.put

    def fail(
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        if metadata.content_schema in (
            "observation-read-result/1",
            "observation-read-result/2",
        ):
            raise OSError("result publication acknowledgement lost")
        return original(data, metadata, control, exchange_id=exchange_id)

    monkeypatch.setattr(case.evidence, "put", fail)
    request = ListObservationRegions(
        request_id="save", snapshot=index.snapshot, output_tokens=1000
    )
    with pytest.raises(ObservationReadUnconfirmed) as caught:
        reads.read(request, op("save"), progress=progress, control=case.control)
    assert (
        caught.value.payload.request == request
        and caught.value.count.measurement.observation_tokens is not None
    )
    assert isinstance(caught.value.primary, OSError) and caught.value.result_ref is None
    before = len(session.body_calls)
    with pytest.raises(OwnershipConflict):
        reads.read(request, op("save-again"), progress=progress, control=case.control)
    assert (
        len(session.body_calls) == before
        and progress.active is None
        and session.calls == 0
    )
    reads.close()
    case.client.close(case.control)


def test_after_publication_revocation_preserves_known_result_without_activating_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = indexed("[1] RootWebArea\n\t[2] button A\n")
    reads, progress, case, gate, session = reader_case(tmp_path, index)
    original = case.evidence.put

    def revoke(
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        reference = original(data, metadata, control, exchange_id=exchange_id)
        if metadata.content_schema in (
            "observation-read-result/1",
            "observation-read-result/2",
        ):
            gate.revoked = True
        return reference

    monkeypatch.setattr(case.evidence, "put", revoke)
    request = ListObservationRegions(
        request_id="known", snapshot=index.snapshot, output_tokens=1000
    )
    with pytest.raises(ObservationReadUnconfirmed) as caught:
        reads.read(request, op("known"), progress=progress, control=case.control)
    assert caught.value.result_ref is not None and progress.active is None
    assert (
        case.evidence.read(caught.value.result_ref, case.control)
        == caught.value.payload.model_dump_json().encode()
    )
    assert session.calls == 0 and len(session.body_calls) == 1
    reads.close()
    case.client.close(case.control)


def test_cancelled_and_foreign_thread_reads_have_no_count_or_publication(
    tmp_path: Path,
) -> None:
    index = indexed("[1] RootWebArea\n")
    reads, progress, case, _, session = reader_case(tmp_path, index)
    request = ListObservationRegions(
        request_id="cancel", snapshot=index.snapshot, output_tokens=1000
    )

    class Cancelled:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "original-read")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    with pytest.raises(OperationStopped):
        reads.read(request, op("cancel"), progress=progress, control=Cancelled())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            reads.read,
            request,
            op("foreign-thread"),
            progress=progress,
            control=case.control,
        )
        with pytest.raises(OwnershipConflict):
            future.result()
    assert not session.body_calls and session.calls == 0 and case.loader.loads == 0
    reads.close()
    case.client.close(case.control)

"""Single-window facts: legitimate reread, shared quota and no false understanding."""

import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.observation_read import (
    ListObservationRegions,
    ReadObservationRegions,
    SearchObservationRegions,
    ObservationRegionRange,
    ObservationReadingDelivery,
)
from lab_generate_skill.domain.observation_read_progress import (
    ObservationReadProgress,
    observation_request_key,
)
from adaptive_observation_fixtures import record
from observation_read_fixtures import indexed
from context_budget_fixtures import ref


def test_a_b_a_restores_only_current_window_and_one_multirange_read_shares_quota() -> (
    None
):
    index = indexed("[1] RootWebArea\n\t[2] button A\n\t[3] button B\n")
    progress = ObservationReadProgress(
        snapshot=index.snapshot, policy=index.policy, records=(), no_progress=0
    )
    a = ReadObservationRegions(
        request_id="a",
        snapshot=index.snapshot,
        output_tokens=100,
        ranges=(ObservationRegionRange(region_id="ax-line-1", unit="whole_region"),),
    )
    b = ReadObservationRegions(
        request_id="b",
        snapshot=index.snapshot,
        output_tokens=100,
        ranges=(ObservationRegionRange(region_id="ax-line-2", unit="whole_region"),),
    )
    for request, body in (
        (a, "A"),
        (b, "B"),
        (a.model_copy(update={"request_id": "a-return"}), "A"),
    ):
        assert progress.identical_active(request) is None
        progress = progress.returned(record(request, body))
    assert progress.reads_used == 3 and progress.no_progress == 0
    assert (
        progress.active is not None and progress.active.request.request_id == "a-return"
    )
    compare = ReadObservationRegions(
        request_id="comparison",
        snapshot=index.snapshot,
        output_tokens=100,
        ranges=(*a.ranges, *b.ranges),
    )
    progress = progress.returned(record(compare, "A and B", tokens=100))
    assert (
        progress.reads_used == 4 and progress.remaining == 2 and progress.warn_remaining
    )
    with pytest.raises(ValueError):
        progress.returned(
            record(
                compare.model_copy(update={"request_id": "oversized"}),
                "oversized comparison",
                tokens=101,
            )
        )


def test_current_window_duplicate_counts_no_progress_but_never_grants_a_dispatch() -> (
    None
):
    index = indexed("[1] RootWebArea\n\t[2] button A\n")
    progress = ObservationReadProgress(
        snapshot=index.snapshot, policy=index.policy, records=(), no_progress=0
    )
    request = ListObservationRegions(
        request_id="directory", snapshot=index.snapshot, output_tokens=100
    )
    progress = progress.returned(record(request, "directory"))
    with pytest.raises(OwnershipConflict):
        progress.require_read(request)
    for identity in ("again", "again-two"):
        fresh = request.model_copy(update={"request_id": identity})
        assert progress.identical_active(fresh) == progress.active
        progress = progress.returned(record(fresh, "directory"))
    assert progress.no_progress == 2 and progress.controlled_stop == "read_no_progress"
    with pytest.raises(ValueError, match="Controlled"):
        progress.require_read(request.model_copy(update={"request_id": "third"}))


def test_directory_search_and_region_read_share_six_and_do_not_reset_on_new_id() -> (
    None
):
    index = indexed("[1] RootWebArea\n\t[2] button A\n")
    progress = ObservationReadProgress(
        snapshot=index.snapshot, policy=index.policy, records=(), no_progress=0
    )
    for i in range(6):
        request = (
            ListObservationRegions(
                request_id=f"read-{i}",
                snapshot=index.snapshot,
                output_tokens=100,
                continuation=None if i == 0 else f"original-directory-page-{i}",
            )
            if i % 2 == 0
            else SearchObservationRegions(
                request_id=f"read-{i}",
                snapshot=index.snapshot,
                output_tokens=100,
                query=str(i),
                region_ids=(),
            )
        )
        progress = progress.returned(
            record(request, f"different directory/search coverage-{i}")
        )
    assert progress.remaining == 0 and progress.controlled_stop is None
    with pytest.raises(ValueError, match="Controlled"):
        progress.require_read(request.model_copy(update={"request_id": "seventh"}))


def test_repeat_identity_includes_snapshot_range_cursor_and_read_options() -> None:
    index = indexed("[1] RootWebArea\n\t[2] button A\n")
    request = SearchObservationRegions(
        request_id="search",
        snapshot=index.snapshot,
        output_tokens=100,
        query="A",
        region_ids=(),
    )
    key = observation_request_key(request)
    assert key == observation_request_key(
        request.model_copy(update={"request_id": "different-id"})
    )
    for changed in (
        {"query": "B"},
        {"region_ids": ("ax-line-1",)},
        {"continuation": "opaque-next"},
        {"output_tokens": 99},
        {"snapshot": index.snapshot.model_copy(update={"sequence": 1})},
    ):
        assert key != observation_request_key(request.model_copy(update=changed))


def test_immutable_old_window_and_foreign_snapshot_cannot_be_rewritten() -> None:
    index = indexed("[1] RootWebArea\n\t[2] button A\n")
    progress = ObservationReadProgress(
        snapshot=index.snapshot, policy=index.policy, records=(), no_progress=0
    )
    a = ListObservationRegions(
        request_id="a", snapshot=index.snapshot, output_tokens=100
    )
    b = SearchObservationRegions(
        request_id="b",
        snapshot=index.snapshot,
        output_tokens=100,
        query="A",
        region_ids=(),
    )
    progress = progress.returned(record(a, "A")).returned(record(b, "B"))
    with pytest.raises(EvidenceIntegrityError):
        progress.returned(
            record(a.model_copy(update={"request_id": "changed-old"}), "Changed A")
        )
    with pytest.raises(OwnershipConflict):
        progress.require_read(
            a.model_copy(
                update={
                    "request_id": "foreign",
                    "snapshot": index.snapshot.model_copy(update={"sequence": 1}),
                }
            )
        )


def test_delivery_distinguishes_returned_from_actual_input_and_never_checked() -> None:
    index = indexed("[1] RootWebArea\n")
    data = dict(
        region="ax-line-0",
        range=index.regions[0].span,
        snapshot=index.snapshot,
        content_ref=ref("observation-read-result/1", "public"),
        model_input_ref=None,
    )
    returned = ObservationReadingDelivery.model_validate(
        data | dict(delivery="returned")
    )
    assert returned.model_input_ref is None
    with pytest.raises(ValidationError):
        ObservationReadingDelivery.model_validate(
            data | dict(delivery="included_in_model_input")
        )
    included = ObservationReadingDelivery.model_validate(
        data
        | dict(
            delivery="included_in_model_input",
            model_input_ref=ref("actor-model-input/1"),
        )
    )
    assert included.model_input_ref is not None
    with pytest.raises(ValidationError):
        ObservationReadingDelivery.model_validate(data | dict(delivery="checked"))

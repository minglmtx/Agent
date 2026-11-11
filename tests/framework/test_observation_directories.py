"""Captured structural directories stay useful within the proposed shared quota."""

import json
import pytest
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.context_preparation import ContextPreparationReceipt
from lab_generate_skill.domain.context_projection import ActorContextSource
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.observation_read import (
    ListObservationRegions,
    ObservationRegionRange,
)
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.policies.observation_index import index_public_ax
from lab_generate_skill.policies.observation_pages import (
    directory_regions,
    observation_page,
)
from lab_generate_skill.policies.observation_search import index_literal_search
from lab_generate_skill.policies.observation_display import observation_read_body
from observation_read_fixtures import indexed, policy
from test_retained_observation_ranges import W, C, body


def test_default_directory_exposes_table_without_enumerating_thousands_of_rows() -> (
    None
):
    index = indexed(
        "[1] RootWebArea\n\t[2] main\n\t\t[3] generic\n\t\t\t[4] table\n"
        + "".join(
            f"\t\t\t\t[{i*2+10}] row\n\t\t\t\t\t[{i*2+11}] gridcell Value-{i}\n"
            for i in range(1000)
        )
    )
    directory = directory_regions(index, None)
    assert len(directory) == 3 and [r.original_node_id for r in directory] == [
        "1",
        "4",
        "2",
    ]
    table = index.region("ax-line-3")
    assert len(table.data_row_spans) == 1000
    expanded = directory_regions(index, "ax-line-1")
    assert [r.original_node_id for r in expanded] == ["3"]
    expanded = directory_regions(index, "ax-line-2")
    assert [r.original_node_id for r in expanded] == ["4"]
    assert directory_regions(index, "ax-line-5") == ()
    with pytest.raises(ValueError):
        directory_regions(index, "ax-line-99999")


def test_directory_parent_is_part_of_cursor_and_repeat_identity() -> None:
    from lab_generate_skill.domain.observation_read_progress import (
        observation_request_key,
    )

    index = indexed("[1] RootWebArea\n\t[2] main\n\t\t[3] button Save\n")
    request = ListObservationRegions(
        request_id="directory", snapshot=index.snapshot, output_tokens=1000
    )
    expanded = request.model_copy(update={"parent_region_id": "ax-line-1"})
    assert observation_request_key(request) != observation_request_key(expanded)
    page = observation_page(
        index,
        expanded,
        offset=0,
        limit=16,
        next_cursor="opaque",
        search=index_literal_search(index),
    )
    assert page.payload.complete and [
        entry.region.original_node_id for entry in page.payload.directory
    ] == ["3"]
    assert '"directory_parent_region":"ax-line-1"' in observation_read_body(
        page.payload
    )


def test_retained_admin_structural_directory_exposes_all_loaded_row_ranges_and_headers() -> (
    None
):
    root = (
        W
        / "experiments/framework-admin-navigation-production-20261102-v1/production-4955553"
    )
    proof = json.loads(
        (
            C / "adaptive-public-source-4957565/source-and-public-structure.json"
        ).read_bytes()
    )
    receipt_path = (
        root
        / "evidence/blobs/86a8e12f3c42dadd11a821a93a094a4706e0ca174d3e8f1558a59262bafdcc30"
    )
    import hashlib

    raw = receipt_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == proof["pins"][str(receipt_path)]
    receipt = ContextPreparationReceipt.model_validate_json(raw)
    source = receipt.request.source
    assert isinstance(source, ActorContextSource) and source.scope.task.split == "train"
    turn = ActorPublicTurn.model_validate_json(body(root, source.turn_ref))
    trace = TraceSnapshot.model_validate_json(
        next((root / "trace").glob("*.trace.json")).read_bytes()
    )
    reference = trace.project().current_observation(trace.plan)
    raw_observation = body(root, reference)
    assert Observation.model_validate_json(raw_observation) == turn.observation.record
    index = index_public_ax(
        reference, raw_observation, turn.observation, source.scope, policy()
    )
    assert len(index.nodes) == 7101
    request = ListObservationRegions(
        request_id="offline-directory-only", snapshot=index.snapshot, output_tokens=8000
    )
    page = observation_page(
        index,
        request,
        offset=0,
        limit=16,
        next_cursor="offline-cursor-not-authority",
        search=index_literal_search(index),
    )
    tables = [
        entry.region for entry in page.payload.directory if entry.region.kind == "table"
    ]
    assert len(tables) == 1 and len(tables[0].data_row_spans) == 200
    assert len(directory_regions(index, None)) < len(index.nodes) // 100
    last = tables[0].data_row_spans[-1]
    selected = ObservationRegionRange(
        region_id="ax-line-0", unit="codepoints", start=last.start, end=last.end
    )
    fragments = index.fragments((selected,))
    assert any(
        fragment.span == last and fragment.purpose == "content"
        for fragment in fragments
    )
    headers = [fragment for fragment in fragments if fragment.purpose == "table_header"]
    assert (
        headers
        and sum(fragment.text.count("columnheader") for fragment in headers) == 15
    )
    assert (
        receipt.decision is not None
        and receipt.decision.assessments[0].input_tokens == 98037
    )

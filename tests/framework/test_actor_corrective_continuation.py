"""Continuation corrections keep the actual request or explicitly lack binding."""

import json
from pathlib import Path
import pytest

from lab_generate_skill.actor.proposal_correction import (
    corrective_proposal_feedback,
    correction_example,
    TEMPLATE_MARKER,
)
from lab_generate_skill.actor.schema_response import current_tool_schemas
from lab_generate_skill.actor.tool_example_binding import (
    ExampleFacts,
    read_format_example,
)
from lab_generate_skill.domain.actor_proposal_feedback import (
    ActorProposalError,
    ActorProposalFeedback,
)
from lab_generate_skill.domain.observation_read import ListObservationRegions
from lab_generate_skill.policies.actor_tool_schemas import materialize_actor_tools
from lab_generate_skill.policies.observation_display import observation_read_body
from observation_read_fixtures import indexed
from state_contract_fixtures import op
from test_snapshot_observation_reads import reader_case
from test_actor_corrective_examples import POLICY
from test_actor_rejected_proposals import completion
from test_actor_tool_schema_response import schema_case


@pytest.mark.parametrize("name", ["list_regions", "read_region", "search_regions"])
def test_unknown_cursor_template_keeps_all_original_request_parameters(
    name: str,
) -> None:
    prompt, task = schema_case(max_identical_invalid_proposals=3)
    assert prompt.observation_view
    original = dict(
        schema_version="observation-read-choice/1",
        tool=name,
        snapshot_sha256=prompt.observation_view.snapshot.observation_ref.sha256,
        output_tokens=7,
        continuation="wrong-original-cursor",
    )
    if name == "list_regions":
        original.update(parent_region_id="ax-line-1")
    elif name == "read_region":
        original.update(
            ranges=[dict(region_id="ax-line-7", unit="codepoints", start=2, end=6)]
        )
    else:
        original.update(
            query="same original query",
            mode="unicode_casefold_literal/1",
            region_ids=["ax-line-7"],
        )
    before = json.dumps(original, sort_keys=True)
    error = ActorProposalError(
        ActorProposalFeedback(
            code="INVALID_CONTINUATION",
            tool=name,
            field="continuation",
            message="No matching issued cursor.",
            next_action="Keep the original request and use only its issued cursor; never guess.",
        )
    )
    feedback = corrective_proposal_feedback(
        error, prompt, completion(prompt, json.dumps({"read": original})), task
    )
    example = correction_example(feedback)
    assert example and TEMPLATE_MARKER in feedback.next_action
    corrected = example["read"]
    assert corrected["continuation"] == "<issued_cursor_for_original_request>"
    assert {
        key: value for key, value in corrected.items() if key != "continuation"
    } == {key: value for key, value in original.items() if key != "continuation"}
    assert json.dumps(original, sort_keys=True) == before


def test_known_issued_cursor_example_passes_the_real_retained_reader_without_spending_a_read(
    tmp_path: Path,
) -> None:
    index = indexed(
        "[1] RootWebArea\n\t[2] button A\n\t[3] button B\n",
        directory_entries=1,
        **POLICY,
    )
    reads, progress, case, _, session = reader_case(tmp_path, index)
    request = ListObservationRegions(
        request_id="directory",
        snapshot=index.snapshot,
        output_tokens=index.policy.body_max_tokens,
    )
    page = reads.automatic_directory(request, op("automatic"), control=case.control)
    assert page.payload.continuation
    body = observation_read_body(
        page.payload,
        current_view="structural_local",
        captured_length=len(index.text),
        read_tools=("list_regions", "read_region", "search_regions"),
    )
    schemas = materialize_actor_tools(
        ("click",),
        ("list_regions", "read_region", "search_regions"),
        index.policy,
        index.snapshot.observation_ref.sha256,
        1,
    )
    example, bound = read_format_example(
        "list_regions", schemas, ExampleFacts(body, None), continuation=True
    )
    assert bound and example["read"]["output_tokens"] == request.output_tokens
    assert example["read"]["continuation"] == page.payload.continuation
    continued = ListObservationRegions(
        request_id="continued",
        snapshot=index.snapshot,
        **{
            key: value
            for key, value in example["read"].items()
            if key not in ("snapshot_sha256", "schema_version")
        },
    )
    reads.check_proposal(continued, progress=progress, control=case.control)
    assert not reads._spent and not session.body_calls
    reads.close()
    case.client.close(case.control)


def test_unknown_cursor_format_does_not_invent_a_new_search_when_original_parameters_are_unavailable() -> (
    None
):
    prompt, task = schema_case(max_identical_invalid_proposals=3)
    example, bound = read_format_example(
        "search_regions",
        current_tool_schemas(prompt, task.allowed_actions),
        ExampleFacts("", None),
        continuation=True,
    )
    assert not bound and example["read"]["query"] == "<original_query>"

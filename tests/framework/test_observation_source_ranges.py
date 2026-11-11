"""Public source/identity/relationship guarantees, not runtime or token savings."""

from dataclasses import replace
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.observation_read import (
    ObservationRegionRange,
    ObservationReadingDelivery,
    ObservationReadFragment,
    ObservationSourceSpan,
)
from lab_generate_skill.policies.observation_index import index_public_ax
from lab_generate_skill.policies.observation_search import literal_search
from observation_read_fixtures import indexed, policy
from observation_fixtures import sample_observation
from retrieval_fixtures import reference
from state_contract_fixtures import scope

TABLE = (
    "RootWebArea 'Products'\n\t[1] navigation 'Navigation'\n\t\t[2] link 'Orders'\n"
    "\t[3] table 'Products'\n\t\t[4] rowgroup ''\n\t\t\t[5] row ''\n"
    "\t\t\t\t[6] columnheader 'SKU'\n\t\t\t\t[7] columnheader 'Price $'\n"
    "\t\t[8] rowgroup ''\n\t\t\t[9] row ''\n\t\t\t\t[10] rowheader 'same'\n"
    "\t\t\t\t[11] gridcell '$0.00' selected\n\t\t\t[12] row ''\n"
    "\t\t\t\t[13] rowheader 'same'\n\t\t\t\t[14] gridcell '' disabled\n"
)


def test_document_focus_keeps_exact_node_state_and_reads_descendants_by_original_ranges() -> (
    None
):
    text = TABLE.replace(
        "RootWebArea 'Products'", "RootWebArea 'Products', focused"
    ).replace("[2] link 'Orders'", "[2] link 'Orders', focused")
    index = indexed(text)
    mandatory = index.mandatory_fragments()
    shown = "".join(f.text for f in mandatory)
    assert (
        "RootWebArea 'Products', focused" in shown
        and "[2] link 'Orders', focused" in shown
    )
    assert not any(f.span == index.regions[0].span for f in mandatory)
    assert "gridcell '$0.00'" not in shown
    table = next(r for r in index.regions if r.kind == "table")
    rows = index.fragments(
        (
            ObservationRegionRange(
                region_id=table.region_id, unit="data_rows", start=0, end=2
            ),
        )
    )
    assert "gridcell '$0.00' selected" in "".join(f.text for f in rows)
    assert "columnheader 'SKU'" in "".join(f.text for f in rows)
    assert all(f.text == text[f.span.start : f.span.end] for f in (*mandatory, *rows))


@pytest.mark.parametrize("role", ["dialog", "alert", "alertdialog"])
def test_document_focus_change_keeps_complete_modal_and_focused_control_subtrees(
    role: str,
) -> None:
    text = (
        "RootWebArea 'Products', focused\n"
        f"\t[1] {role} 'Required notice'\n\t\t[2] StaticText 'Do not lose the complete public notice'\n"
        "\t[3] textbox 'Current input', focused\n\t\t[4] StaticText 'Current full value'\n"
    )
    index = indexed(text)
    shown = "".join(f.text for f in index.mandatory_fragments())
    assert (
        "Do not lose the complete public notice" in shown
        and "Current full value" in shown
    )
    assert all(
        f.text == text[f.span.start : f.span.end] for f in index.mandatory_fragments()
    )


def test_complete_row_selection_keeps_headers_ancestors_values_and_distinct_ids() -> (
    None
):
    index = indexed(TABLE)
    table = next(region for region in index.regions if region.kind == "table")
    assert len(table.data_row_spans) == 2 and len(table.header_spans) == 1
    ranges = (
        ObservationRegionRange(
            region_id=table.region_id, unit="data_rows", start=0, end=2
        ),
    )
    pieces = index.fragments(ranges)
    text = "".join(piece.text for piece in pieces)
    assert all(
        x in text
        for x in [
            "[6] columnheader 'SKU'",
            "[7] columnheader 'Price $'",
            "[10] rowheader 'same'",
            "[13] rowheader 'same'",
            "'$0.00' selected",
            "gridcell '' disabled",
        ]
    )
    for piece in pieces:
        assert piece.text == TABLE[piece.span.start : piece.span.end]
    # Reading a row directly has the same required original header context.
    row = index.at(TABLE.index("[13] rowheader"))
    direct = index.fragments(
        (ObservationRegionRange(region_id=row.region_id, unit="whole_region"),)
    )
    assert any(
        piece.purpose == "table_header" and "columnheader" in piece.text
        for piece in direct
    )
    assert len(literal_search(index, "same", ()).hits) == 2


def test_cross_range_order_and_codepoint_boundaries_do_not_trim_unicode_or_code() -> (
    None
):
    text = "RootWebArea 'Code'\n\t[1] code 'path=main.py ref=public'\n\t\tStaticText 'def f():\\n    return 🧭\\n'\n\t[2] code 'path=other.py ref=public'\n\t\tStaticText '    pass'\n"
    index = indexed(text)
    codes = [r for r in index.regions if r.kind == "code"]
    fragments = index.fragments(
        tuple(
            ObservationRegionRange(region_id=r.region_id, unit="whole_region")
            for r in reversed(codes)
        )
    )
    assert "".join(f.text for f in fragments) == text
    assert "\\n    return 🧭\\n" in fragments[1].text
    code = codes[0]
    at = text.index("🧭") - code.span.start
    selected = ObservationRegionRange(
        region_id=code.region_id, unit="codepoints", start=at, end=at + 1
    )
    fragments = index.fragments((selected,))
    assert any(f.purpose == "content" and f.text == "🧭" for f in fragments)
    assert any(
        f.purpose == "row_identity" and "path=main.py ref=public" in f.text
        for f in fragments
    )


def test_comment_subtree_preserves_parent_identity_and_equal_sibling_text() -> None:
    text = "RootWebArea 'Comments'\n\t[1] article 'author=A'\n\t\tStaticText 'same'\n\t\t[2] article 'author=B reply_to=1'\n\t\t\tStaticText 'same'\n\t[3] article 'author=C'\n\t\tStaticText 'same'\n"
    index = indexed(text)
    hits = literal_search(index, "SAME", ())
    assert len(hits.hits) == 3 and len({x.region_id for x in hits.hits}) == 3
    child = index.region(hits.hits[1].region_id)
    fragments = index.fragments(
        (ObservationRegionRange(region_id=child.region_id, unit="whole_region"),)
    )
    assert "author=A" in "".join(x.text for x in fragments)
    assert "author=B reply_to=1" in "".join(x.text for x in fragments)
    assert "author=C" not in "".join(x.text for x in fragments)


def test_search_literal_unicode_source_offsets_and_coverage_pagination() -> None:
    text = "RootWebArea 'Search'\n\t[1] paragraph 'Straße STRASSE .* Straße'\n\t[2] paragraph 'café café'\n"
    index = indexed(text, search_hits=1)
    first = literal_search(index, "STRASSE", ())
    assert (
        len(first.hits) == 1
        and not first.results_exhausted
        and not first.coverage_complete
    )
    assert index.source(first.hits[0].match_span) == "Straße"
    assert first.next_folded_offset is not None
    second = literal_search(
        index, "STRASSE", (), after_folded_offset=first.next_folded_offset
    )
    assert index.source(second.hits[0].match_span) == "STRASSE"
    assert second.next_folded_offset is not None
    third = literal_search(
        index, "STRASSE", (), after_folded_offset=second.next_folded_offset
    )
    assert (
        index.source(third.hits[0].match_span) == "Straße" and third.results_exhausted
    )
    literal = literal_search(index, ".*", ())
    assert len(literal.hits) == 1 and index.source(literal.hits[0].match_span) == ".*"
    assert (
        len(literal_search(index, "CAFÉ", ()).hits) == 1
    )  # No implicit NFC/NFKC/accent folding.
    missing = literal_search(index, "not-on-this-captured-page", ())
    assert missing.results_exhausted and missing.coverage_complete and not missing.hits
    assert missing.inspected_coverage == (
        ObservationSourceSpan(start=0, end=len(text)),
    )


@pytest.mark.parametrize(
    "bad",
    [
        None,
        True,
        0,
        {},
        [],
        "\tbad\n",
        "Root\n  [1] button 'x'\n",
        "Root\n\t\t[1] button 'x'\n",
    ],
)
def test_invalid_or_unsupported_structure_refuses_without_a_new_capture(
    bad: Any,
) -> None:
    with pytest.raises((ValueError, TypeError, ValidationError)):
        indexed(bad)


def test_explicit_empty_observation_has_no_fabricated_regions_or_hits() -> None:
    index = indexed("")
    assert index.regions == () and index.text == ""
    result = literal_search(index, "x", ())
    assert not result.hits and result.coverage_complete and result.results_exhausted


def test_full_reference_scope_and_frozen_unicode_version_cannot_be_substituted() -> (
    None
):
    state = scope()
    record = sample_observation(
        state.task, state.context_id, state.attempt_id
    ).model_copy(update={"text": TABLE})
    raw = record.model_dump_json().encode()
    from lab_generate_skill.domain.observation import ResolvedObservation

    resolved = ResolvedObservation(record=record, text=TABLE)
    ref = reference(record, "observation/1", "public")
    with pytest.raises(EvidenceIntegrityError):
        index_public_ax(ref, raw + b" ", resolved, state, policy())
    with pytest.raises(OwnershipConflict):
        index_public_ax(
            ref,
            raw,
            resolved,
            state.model_copy(update={"context_id": "foreign"}),
            policy(),
        )
    with pytest.raises(ValueError, match="Unicode"):
        index_public_ax(ref, raw, resolved, state, policy(unicode_version="0.0"))
    with pytest.raises(ValueError, match="frame"):
        index_public_ax(ref, raw, resolved, state, policy(), frame_id="invented-main")
    index = indexed(TABLE)
    with pytest.raises(OwnershipConflict):
        index.require_snapshot(index.snapshot.model_copy(update={"tab_id": "foreign"}))
    with pytest.raises(ValueError):
        index.region("ax-line-0001")
    table = next(x for x in index.regions if x.kind == "table")
    with pytest.raises(ValueError):
        index.selected_spans(
            ObservationRegionRange(
                region_id=table.region_id, unit="data_rows", start=0, end=3
            )
        )


def test_proposed_capacity_limits_are_distinct_and_delivery_never_claims_understanding() -> (
    None
):
    configured = policy()
    assert (
        configured.switch_tokens,
        configured.body_target_tokens,
        configured.body_max_tokens,
    ) == (24576, 6000, 8000)
    index = indexed(TABLE)
    content_ref = reference({"unit": "public"}, "observation-read-result/1", "public")
    value = dict(
        region="ax-line-0",
        range=ObservationSourceSpan(start=0, end=1),
        snapshot=index.snapshot,
        delivery="returned",
        content_ref=content_ref,
        model_input_ref=None,
    )
    assert ObservationReadingDelivery.model_validate(value).delivery == "returned"
    with pytest.raises(ValidationError):
        ObservationReadingDelivery.model_validate(value | {"delivery": "checked"})
    with pytest.raises(ValidationError):
        ObservationReadingDelivery.model_validate(
            value | {"delivery": "included_in_model_input"}
        )
    actual = ObservationReadingDelivery.model_validate(
        value
        | {
            "delivery": "included_in_model_input",
            "model_input_ref": reference(
                {"unit": "actual-input"}, "actor-model-input/1"
            ),
        }
    )
    assert actual.model_input_ref is not None
    with pytest.raises(ValidationError):
        ObservationReadFragment(
            span=ObservationSourceSpan(start=0, end=2), purpose="content", text="x"
        )


def test_actual_attribute_separator_is_preserved_and_unknown_article_is_not_a_comment() -> (
    None
):
    text = "RootWebArea 'x'\n\t[1] generic, native_clickable=True\n\t\t[2] article 'public-body'\n\t\t\tStaticText 'text'\n"
    index = indexed(text)
    assert index.nodes[1].role == "generic"
    assert index.regions[2].kind == "ax_subtree"
    fragments = index.fragments(
        (ObservationRegionRange(region_id="ax-line-2", unit="whole_region"),)
    )
    assert "".join(x.text for x in fragments) == text
    with pytest.raises(ValueError):
        indexed("not-AX-plain-text")
    with pytest.raises(ValueError):
        indexed("RootWebArea 'x'\n\t[1] generic; native_clickable=True\n")


def test_literal_query_rejects_unpaired_unicode_before_read_or_wire_delivery() -> None:
    index = indexed(TABLE)
    with pytest.raises(UnicodeError):
        literal_search(index, "\ud800", ())
    from lab_generate_skill.domain.observation_read import SearchObservationRegions

    with pytest.raises((ValidationError, UnicodeError)):
        SearchObservationRegions(
            request_id="bad-query",
            snapshot=index.snapshot,
            output_tokens=8000,
            query="\ud800",
            region_ids=(),
        )

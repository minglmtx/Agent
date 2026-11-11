"""Shared graph boundary: declared fields only, stable order and no JSON guessing."""

from lab_generate_skill.domain.evidence_dependencies import evidence_references
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.validation import Contract
from retrieval_fixtures import reference


class Declared(Contract):
    first: EvidenceRef
    nested: tuple[EvidenceRef, ...]
    opaque: dict[str, object]


def test_declared_graph_preserves_order_and_duplicates() -> None:
    first = reference({"first": True})
    second = reference({"second": True})
    value = Declared(first=first, nested=(second, first), opaque={"hidden": second})
    assert evidence_references((value, None)) == (first, second, first)


def test_opaque_values_are_not_interpreted_as_contract_links() -> None:
    ref = reference({"reference": True})
    for value in (ref.model_dump(), [ref], ref.uri, None, True, b"cas://sha256/test"):
        assert evidence_references(value) == ()
    assert evidence_references(ref) == (ref,)

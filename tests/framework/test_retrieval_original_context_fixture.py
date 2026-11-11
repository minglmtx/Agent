"""Fixture declares exact original public-context bytes before generating query lineage."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.evidence import EvidenceMetadata
from evidence_control_fixtures import EvidenceFixtureStore
from retrieval_fixtures import fixture


@pytest.mark.parametrize(
    "fault", ["none", "visibility", "schema", "body", "missing-context", "wrong-type"]
)
def test_original_reference_is_bound_before_fixture_publication(
    tmp_path: Path, fault: str
) -> None:
    store = EvidenceFixtureStore(tmp_path)
    original = fixture(store)
    context = original.context
    ref: Any = store.put(
        context.model_dump_json().encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="public-construction-context/1",
            visibility="public",
            producer="original-context-source",
        ),
    )
    assert ref != original.query.public_context_ref
    if fault == "visibility":
        ref = ref.model_copy(update={"visibility": "private"})
    elif fault == "schema":
        ref = ref.model_copy(update={"content_schema": "wrong-context/1"})
    elif fault == "body":
        context = context.model_copy(update={"context_id": "different-source"})
    elif fault == "wrong-type":
        ref = True
    before = set(tmp_path.rglob("*"))
    if fault != "none":
        with pytest.raises(ValueError):
            fixture(
                store,
                public_context=None if fault == "missing-context" else context,
                public_context_ref=ref,
            )
        assert set(tmp_path.rglob("*")) == before
    else:
        selected = fixture(store, public_context=context, public_context_ref=ref)
        assert (
            selected.query.public_context_ref
            == selected.result.query.public_context_ref
            == ref
        )

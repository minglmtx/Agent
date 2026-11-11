"""Explicit run/source namespaces, persistent isolation and legacy refusal."""

import hashlib
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.evidence_sessions import EvidenceSessionBinding
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from evidence_session_fixtures import binding, capacity, intent
from evidence_session_storage_fixtures import store, snapshot_path


def run_binding() -> EvidenceSessionBinding:
    return EvidenceSessionBinding.model_validate(
        {**binding().model_dump(), "scope": "run", "source_task_id": None}
    )


def test_source_namespace_stays_at_original_filename() -> None:
    original = binding()
    legacy_key = hashlib.sha256(
        json.dumps(
            [original.storage_id, original.source_task_id], separators=(",", ":")
        ).encode()
    ).hexdigest()
    assert original.namespace_key == legacy_key
    assert run_binding().namespace_key != legacy_key
    assert original.schema_version == "evidence-session-binding/2"


@pytest.mark.parametrize(
    "scope,source",
    [
        ("run", "source-1"),
        ("source", None),
        ("source", ""),
        ("source", []),
        ("other", None),
        (None, None),
        (False, None),
    ],
)
def test_invalid_scope_is_never_inferred(scope: object, source: object) -> None:
    with pytest.raises(ValidationError):
        EvidenceSessionBinding.model_validate(
            {**binding().model_dump(), "scope": scope, "source_task_id": source}
        )


@pytest.mark.parametrize("missing", ["scope", "source_task_id"])
def test_scope_and_null_source_are_explicit(missing: str) -> None:
    data = run_binding().model_dump()
    del data[missing]
    with pytest.raises(ValidationError):
        EvidenceSessionBinding.model_validate(data)


def test_run_namespace_ignores_session_and_owner_aliases() -> None:
    original = run_binding()
    for update in (
        {"session_id": "another"},
        {
            "owner": original.owner.model_copy(
                update={"owner_id": "another", "worker_id": "another"}
            )
        },
    ):
        assert (
            original.model_copy(update=update).namespace_key == original.namespace_key
        )
    changed_run = original.model_copy(
        update={"owner": original.owner.model_copy(update={"run_id": "another-run"})}
    )
    assert changed_run.namespace_key != original.namespace_key


def test_run_and_sources_keep_distinct_actual_histories(tmp_path: Path) -> None:
    ledger = store(tmp_path)
    run, source = run_binding(), binding()
    op = intent().operation
    ledger.create(run, capacity(), op)
    ledger.create(source, capacity(), op)
    ledger.begin(run, intent(), 0)
    assert ledger.read(run, op).revision == 1
    assert ledger.read(source, op).revision == 0
    other = run.model_copy(update={"session_id": "another"})
    with pytest.raises(OwnershipConflict):
        ledger.create(other, capacity(), op)
    assert ledger.read(run, op).entries[0].intent == intent()


@pytest.mark.parametrize("pending", [False, True])
def test_legacy_snapshot_is_not_bypassed_or_rewritten(
    tmp_path: Path, pending: bool
) -> None:
    ledger = store(tmp_path)
    current = binding()
    original = intent()
    saved = ledger.create(current, capacity(), original.operation)
    if pending:
        saved = ledger.begin(current, original, 0)
    # Exact historical representation: /1 binding had no explicit scope.
    legacy = saved.model_dump(mode="json")
    legacy["schema_version"] = "evidence-session-snapshot/1"
    legacy["binding"]["schema_version"] = "evidence-session-binding/1"
    del legacy["binding"]["scope"]
    raw = json.dumps(legacy, separators=(",", ":")).encode()
    path = snapshot_path(tmp_path)
    path.write_bytes(raw)
    files = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    for action in ("read", "create"):
        with pytest.raises(EvidenceIntegrityError):
            if action == "read":
                ledger.read(current, original.operation)
            else:
                ledger.create(current, capacity(), original.operation)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == files

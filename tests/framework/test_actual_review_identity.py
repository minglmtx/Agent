"""Shared review optional identity guard precedes trace/goal/native evidence reads."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from pydantic import ValidationError
import admin_actor_review_live as review
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.identity import TaskIdentity
from gitlab_source_selection import group_selection, ssh_selection


class ReachedOriginalScope(Exception):
    pass


class RequestDouble:
    def __init__(self, identity: TaskIdentity) -> None:
        self.task = SimpleNamespace(identity=identity)

    @property
    def scope(self) -> Any:
        raise ReachedOriginalScope(
            "unchanged original reviewer follows the identity gate"
        )


@pytest.mark.parametrize("mode", ["default", "matching", "different"])
def test_shared_review_identity_guard_rejects_mismatch_and_preserves_existing_default(
    mode: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor_root = tmp_path / "gitlab-actor-native"
    actor_root.mkdir()
    ref = EvidenceRef(
        uri="unit:planned-request",
        sha256="0" * 64,
        size_bytes=1,
        media_type="application/json",
        content_schema="actor-run-request/1",
        visibility="private",
        producer="unit",
    )
    (actor_root / "facts.json").write_text(
        json.dumps(
            {
                "software_receipt": "/unused",
                "actor": {"planned_actor_request_ref": ref.model_dump(mode="json")},
            }
        )
    )
    (tmp_path / "registered-site-actor_source.json").write_text("{}")
    monkeypatch.setattr(review, "verify_source", lambda *a, **k: None)
    monkeypatch.setattr(review, "ReadOnlyEvidence", lambda *a, **k: object())
    selected = group_selection().public_template.identity
    reads: list[bool] = []

    def read(*args: Any, **kwargs: Any) -> Any:
        assert not reads
        reads.append(True)
        return RequestDouble(selected)

    monkeypatch.setattr(review, "read_fact", read)
    expected = (
        None
        if mode == "default"
        else (
            selected if mode == "matching" else ssh_selection().public_template.identity
        )
    )
    error = OwnershipConflict if mode == "different" else ReachedOriginalScope
    with pytest.raises(error):
        review.review_actual_actor_attempt(
            tmp_path, gitlab=True, expected_identity=expected
        )
    assert len(reads) == 1


@pytest.mark.parametrize("bad", [{}, [], "", 1, False])
def test_bad_expected_identity_refused_before_any_retained_file_read(
    bad: Any, tmp_path: Path
) -> None:
    absent = tmp_path / "must-not-be-read"
    with pytest.raises(ValidationError):
        review.review_actual_actor_attempt(absent, gitlab=True, expected_identity=bad)
    assert not absent.exists()

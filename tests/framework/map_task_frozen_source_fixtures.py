"""Freeze independent small native source BEFORE constructing its candidate.

All kernel/permission/browser source facts remain explicit unit premises.
Unlike the old coupled fixture, the candidate worker is never the source worker.
The full native state digest and public URL are kept unchanged and compared by
the original strict NavigationInitialComparison; no baseline adjustment.
"""

from pathlib import Path
from typing import Any
import json
import pytest
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
)
from evidence_control_fixtures import EvidenceFixtureStore
from map_task_preparation_port_fixtures import preparation_case
from task_initialization_source_fixtures import historical_source
from test_site_resource import inspect

FrozenSource = tuple[PublicContextInputs, PublicContextReceipt, EvidenceRef]


def frozen_map_unit_source(
    root: Path, patch: pytest.MonkeyPatch, source_id: str
) -> tuple[FrozenSource, EvidenceFixtureStore]:
    root.mkdir()
    with patch.context() as isolated:
        with preparation_case(root, isolated, source_id) as source:
            frozen = historical_source(source)
            resource = source.original.resource
            assert source.requests == []
        assert inspect(resource).state == "closed"
        assert len(resource.channels) == 1 and resource.channels[0].starts == 1
    return frozen, resource.evidence


def copy_frozen_source(
    frozen: FrozenSource, source: EvidenceFixtureStore, target: EvidenceFixtureStore
) -> None:
    visited: set[EvidenceRef] = set()

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            if {
                "uri",
                "sha256",
                "size_bytes",
                "media_type",
                "content_schema",
                "visibility",
                "producer",
            } <= set(value):
                ref = EvidenceRef.model_validate(value)
                if ref in visited:
                    return
                visited.add(ref)
                raw = source.read(ref)
                metadata = EvidenceMetadata.model_validate(
                    ref.model_dump(
                        include={
                            "media_type",
                            "content_schema",
                            "visibility",
                            "producer",
                        }
                    )
                )
                assert target.put(raw, metadata) == ref
                if ref.media_type == "application/json":
                    visit(json.loads(raw))
            else:
                for item in value.values():
                    visit(item)

    for model in frozen:
        visit(model.model_dump(mode="json"))

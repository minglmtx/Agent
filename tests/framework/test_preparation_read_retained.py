"""Original failed Map preparation through the actual installed graph consumer."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.closed_source_protocol import decode_command
from lab_generate_skill.domain.preparation_read import (
    PreparationReadRequest,
    PreparationReadBodies,
)
from lab_generate_skill.domain.closed_source_read import ClosedMapReadMaterial
from lab_generate_skill.domain.errors import InvalidTransition
from closed_source_read_fixtures import actual_read_case
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from initialization_binding_retained_fixtures import retained_inputs, CASES, W


@pytest.fixture(scope="module")
def retained() -> dict[str, Any]:
    old = CASES["Map"]
    try:
        CASES["Map"] = (old[0], 4925677)
        result = retained_inputs("Map")
    finally:
        CASES["Map"] = old
    root = W / "experiments" / old[0] / "production-4925677"
    result["root"] = root
    result["material"] = decode_command(
        (root / "source-read/last-request.json").read_bytes()
    ).material
    return result


def test_retained_preparation_is_read_by_fixed_worker_without_leaf_exchange_or_replay(
    tmp_path: Path, installed_sources: InstalledFixture, retained: dict[str, Any]
) -> None:
    material = retained["material"]
    assert isinstance(material, ClosedMapReadMaterial)
    case = actual_read_case(
        tmp_path, installed_sources, retained=(material, retained["root"] / "evidence")
    )
    selected = PreparationReadRequest(
        selection=retained["original"].publication.selection,
        operation=retained["request"].operation,
    )
    context = case.transport.read(
        material, case.controls.bind(case.op), preparation_read=selected
    )
    reply = case.transport.last_reply
    assert reply is not None and reply.preparation_bodies is not None
    bodies = reply.preparation_bodies
    assert bodies.request == selected and context == retained["source"]
    assert bodies.inputs.request == retained["request"]
    assert bodies.inputs.environment == retained["environment"]
    assert reply.schema_version == "closed-source-read-reply/4"
    assert len(case.transport.timings) == 1
    assert (
        case.transport.last_capture is not None
        and case.transport.last_capture.termination is not None
    )
    assert case.transport.last_capture.termination.state == "reaped"
    # Shape and exact-byte failures refuse before any second child/website call.
    for field, value in [
        ("private_spec_json", "{}"),
        ("snapshot_json", "{}"),
        ("verified", ()),
    ]:
        with pytest.raises(ValueError):
            PreparationReadBodies.model_validate({**bodies.model_dump(), field: value})
    case.current.admission.stop_new_io()
    with pytest.raises(InvalidTransition):
        case.transport.read(
            material, case.controls.bind(case.op), preparation_read=selected
        )
    assert len(case.transport.timings) == 1

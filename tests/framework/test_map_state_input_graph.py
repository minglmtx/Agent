"""Same original Map state algorithms, complete graph and no native delegation."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.adapters.map_artifacts.state_input_protocol import (
    decode_command,
)
from lab_generate_skill.adapters.map_artifacts.state_input_graph import (
    MapStateInputCollector,
)
from lab_generate_skill.adapters.map_artifacts.state_input_bodies import (
    MapStateBodyReader,
)
from lab_generate_skill.bootstrap.deferred_state_records import (
    DeferredStateQualificationChecks,
)
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.map_state_inputs import (
    MapStateInputBody,
    MapStateInputBodies,
)
from lab_generate_skill.domain.errors import (
    EvidenceNotFound,
    InvalidTransition,
    EvidenceIntegrityError,
    OwnershipConflict,
)
from lab_generate_skill.sites.map.tasks.overlay_state_checks import OverlayStateChecks
from map_registered_worker_fixtures import RegisteredMapCase
from map_qualification_fixtures import qualified, restore
from map_navigation_group_cases import SOURCES
from map_state_input_fixtures import CountNativeFiles
from preparation_record_fixtures import put
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "raw", [b"", b"{}", b"[]", b"null", b"true", b"\xff", None, "{}"]
)
def test_missing_illegal_or_wrong_type_command_refused(raw: Any) -> None:
    with pytest.raises(ValueError):
        decode_command(raw)


def test_body_count_and_total_byte_bounds_preserve_complete_records() -> None:
    def body(raw: bytes, name: str) -> MapStateInputBody:
        ref = evidence_reference(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema="unit-state/1",
                visibility="private",
                producer=name,
            ),
        )
        return MapStateInputBody(reference=ref, text=raw.decode())

    values = tuple(body(b"{}", "unit-" + str(i)) for i in range(64))
    assert len(MapStateInputBodies(bodies=values).bodies) == 64
    with pytest.raises(ValueError):
        MapStateInputBodies(bodies=(*values, body(b"{}", "unit-64")))
    raw = ('{"x":"' + "a" * 100000 + '"}').encode()
    with pytest.raises(ValueError):
        MapStateInputBodies(
            bodies=tuple(body(raw, "large-" + str(i)) for i in range(64))
        )


@pytest.mark.parametrize("source", SOURCES)
def test_group_branch_graph_preserves_environment_reset_and_native_permissions(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=source)
    try:
        with qualified(c, monkeypatch) as q:
            c.observer = "controller"
            deferred = q.qualifications.checks
            assert isinstance(deferred, DeferredStateQualificationChecks)
            old = deferred.original()
            assert isinstance(old, OverlayStateChecks)
            for kind in ("environment", "reset"):
                selection = q.environment if kind == "environment" else restore(q)
                reference = (
                    q.environment_ref
                    if kind == "environment"
                    else put(c.resource.evidence, selection)
                )
                expected_files = CountNativeFiles(old.files)
                actual_files = CountNativeFiles(old.files)
                expected = OverlayStateChecks(
                    c.resource.evidence, expected_files, old.site, old.started
                )
                body_values = MapStateInputCollector(
                    c.resource.evidence, guard(60)
                ).collect(selection, reference, c.scope.task)
                reader = MapStateBodyReader(body_values, guard(60))
                actual = OverlayStateChecks(reader, actual_files, old.site, old.started)
                sql = len(c.sql.calls)
                if isinstance(selection, EnvironmentSelection):
                    assert actual.environment(
                        selection,
                        reference,
                        q.preparation.environment.operation,
                        guard(60),
                    ) == expected.environment(
                        selection,
                        reference,
                        q.preparation.environment.operation,
                        guard(60),
                    )
                else:
                    assert actual.reset(
                        selection, reference, guard(60)
                    ) == expected.reset(selection, reference, guard(60))
                assert actual_files.calls == expected_files.calls and actual_files.calls
                assert len(c.sql.calls) == sql
                reader.close()
                with pytest.raises(InvalidTransition):
                    reader.read(reference, guard())
    finally:
        c.close_sockets()


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "corrupt",
        "wrong_root",
        "metadata",
        "duplicate",
        "empty",
        "wrong_type",
        "scope",
    ],
)
def test_invalid_or_incomplete_graph_fails_closed_before_native(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        with qualified(c, monkeypatch) as q:
            c.observer = "controller"
            collector = MapStateInputCollector(c.resource.evidence, guard(60))
            env, ref = q.environment, q.environment_ref
            if fault in ("missing", "corrupt"):

                class BrokenRead:
                    def read(self, reference: Any, local: Any) -> bytes:
                        if reference == env.spec_ref:
                            if fault == "missing":
                                raise EvidenceNotFound(
                                    "original referenced object missing"
                                )
                            return b"corrupt"
                        return c.resource.evidence.read(reference, local)

                collector = MapStateInputCollector(BrokenRead(), guard(60))
                with pytest.raises(
                    (EvidenceNotFound, EvidenceIntegrityError, ValueError)
                ):
                    collector.collect(env, ref, c.scope.task)
                return
            if fault == "wrong_root":
                with pytest.raises(ValueError):
                    collector.collect(env, env.spec_ref, c.scope.task)
                return
            if fault == "scope":
                with pytest.raises((ValueError, OwnershipConflict)):
                    collector.collect(
                        env,
                        ref,
                        c.scope.task.model_copy(update={"source_task_id": "foreign"}),
                    )
                return
            bodies = collector.collect(env, ref, c.scope.task)
            if fault == "duplicate":
                with pytest.raises(ValueError):
                    MapStateInputBodies(bodies=(*bodies.bodies, bodies.bodies[0]))
            elif fault == "empty":
                with pytest.raises(ValueError):
                    MapStateInputBodies(bodies=())
            elif fault == "wrong_type":
                with pytest.raises(ValueError):
                    MapStateInputBody.model_validate({"reference": ref, "text": True})
            else:
                first = bodies.bodies[0]
                reader = MapStateBodyReader(
                    MapStateInputBodies(
                        bodies=(
                            first.model_copy(
                                update={
                                    "reference": first.reference.model_copy(
                                        update={"producer": "foreign"}
                                    )
                                }
                            ),
                            *bodies.bodies[1:],
                        )
                    ),
                    guard(),
                )
                with pytest.raises(EvidenceNotFound):
                    reader.read(ref, guard())
    finally:
        c.close_sockets()

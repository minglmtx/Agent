"""Exact downstream read counts, original native checks and fresh authority."""

from collections import Counter
import json
import os
from pathlib import Path
from typing import Any

import pytest

from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OperationStopped
from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.map_state_artifact import MapStateArtifact
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_state_artifacts import MapStateFileReader
from lab_generate_skill.sites.map.tasks.navigation_preparation_checks import (
    NavigationPreparationChecks,
)
from map_registered_worker_fixtures import RegisteredMapCase
from map_navigation_group_cases import SOURCES
from map_navigation_prepared_fixtures import prepare_navigation
from preparation_record_fixtures import fixture
from site_instance_fixtures import node_path as node_path
from test_site_resource import enter
from test_slurm_commands import guard


class NativeReads:
    def __init__(self, original: MapStateFileReader) -> None:
        self.original = original
        self.calls: list[MapStateArtifact] = []

    def read(
        self,
        descriptor: MapStateArtifact,
        request: SiteTaskRequest,
        control: OperationControl,
    ) -> bytes:
        self.calls.append(descriptor)
        return self.original.read(descriptor, request, control)


def test_same_preparation_facts_fewer_exchanges_original_native_checks_and_repeat(
    node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        with enter(c.resource) as live:
            p = prepare_navigation(c, live)
            c.observer = "controller"
            try:
                reader = p.records.reader
                checker = p.records.checks
                assert isinstance(checker, NavigationPreparationChecks)
                files = NativeReads(checker.files)
                checker.files = files
                original = c.resource.evidence.read
                reads: Counter[EvidenceRef] = Counter()

                def counted(ref: EvidenceRef, control: Any = None) -> bytes:
                    reads[ref] += 1
                    raw = original(ref, control=control)
                    assert type(raw) is bytes
                    return raw

                monkeypatch.setattr(c.resource.evidence, "read", counted)
                control = guard()
                # Prior downstream public calls, retained as a count reference:
                # load graph, recompute checker, then read its dependencies.
                inputs = reader.load(
                    p.publication.selection, p.request.operation, control
                )
                checks = checker.check(inputs, control)
                reader.reads.dependencies((checks,), control)
                old, old_files = dict(reads), tuple(files.calls)
                reads.clear()
                files.calls.clear()
                loaded, receipt = p.records._verify(
                    p.publication.selection, p.request.operation, control
                )
                assert loaded == inputs and receipt.checks == checks
                assert tuple(files.calls) == old_files
                new = dict(reads)
                assert inputs.request.snapshot_ref is not None
                assert sum(old.values()) - sum(new.values()) == 7
                assert reads[inputs.binding.private_spec_ref] == 1
                assert reads[inputs.request.snapshot_ref] == 1
                reads.clear()
                assert p.records._verify(
                    p.publication.selection, p.request.operation, control
                ) == (loaded, receipt)
                assert dict(reads) == new
                Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]).joinpath(
                    "preparation-body-handoff-counts.json"
                ).write_text(
                    json.dumps(
                        {
                            "prior_reads": sum(old.values()),
                            "current_reads": sum(new.values()),
                            "native_reads_per_call": len(old_files),
                            "private_reads_per_call": new[
                                inputs.binding.private_spec_ref
                            ],
                            "snapshot_reads_per_call": new[inputs.request.snapshot_ref],
                            "scope": "Original preparation semantic/native checks, isolated software fixture; no production speed claim or cross-call cache.",
                        },
                        indent=2,
                    )
                    + "\n"
                )
            finally:
                c.observer = "worker"
    finally:
        c.close_sockets()


@pytest.mark.parametrize(
    "fault", ["private", "snapshot", "empty", "type", "cancel", "fallback"]
)
def test_map_handoff_rechecks_complete_bytes_and_keeps_original_fallback(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = RegisteredMapCase(node_path, monkeypatch, navigation_source=SOURCES[0])
    try:
        with enter(c.resource) as live:
            p = prepare_navigation(c, live)
            c.observer = "controller"
            try:
                loaded = p.records.reader.load_with_bodies(
                    p.publication.selection, p.request.operation, guard()
                )
                checker = p.records.checks
                assert isinstance(checker, NavigationPreparationChecks)
                assert loaded.private_spec and loaded.snapshot
                private: Any = loaded.private_spec
                snapshot: Any = loaded.snapshot
                if fault == "private":
                    private = b"bad"
                if fault == "snapshot":
                    snapshot = b"bad"
                if fault == "empty":
                    private = b""
                if fault == "type":
                    snapshot = loaded.snapshot.decode()
                if fault == "fallback":
                    private = snapshot = None

                class Cancel:
                    def checkpoint(self) -> float:
                        raise OperationStopped("CANCELLED", "preparation-body-handoff")

                    def wait(self, seconds: float) -> None:
                        self.checkpoint()

                if fault == "fallback":
                    assert checker.check_with_bodies(
                        loaded.inputs, None, None, guard()
                    ) == checker.check(loaded.inputs, guard())
                else:
                    with pytest.raises((EvidenceIntegrityError, OperationStopped)):
                        checker.check_with_bodies(
                            loaded.inputs,
                            private,
                            snapshot,
                            Cancel() if fault == "cancel" else guard(),
                        )
            finally:
                c.observer = "worker"
    finally:
        c.close_sockets()


@pytest.mark.parametrize("fault", ["extra_dependency", "authority_revoked", "cancel"])
def test_generic_verification_checks_new_dependencies_and_live_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    c = fixture(tmp_path)
    original_checks = c.adapter.checks
    extra = c.store.put(
        b"extra",
        EvidenceMetadata(
            media_type="text/plain",
            content_schema="handoff-extra/1",
            visibility="private",
            producer="unit",
        ),
        control=guard(),
    )
    calls: list[EvidenceRef] = []
    original_read = c.store.read

    def read(ref: EvidenceRef, control: Any = None) -> bytes:
        calls.append(ref)
        raw = original_read(ref, control=control)
        assert type(raw) is bytes
        return raw

    monkeypatch.setattr(c.store, "read", read)

    class BodyChecks:
        def check(
            self, inputs: PreparationInputs, control: OperationControl
        ) -> StateChecks:
            raise AssertionError("Explicit body consumer must be used")

        def check_with_bodies(
            self,
            inputs: PreparationInputs,
            private_spec: bytes | None,
            snapshot: bytes | None,
            control: OperationControl,
        ) -> StateChecks:
            assert private_spec is not None and snapshot is not None
            result = original_checks.check(inputs, control)
            if fault == "authority_revoked":
                c.authority.denied = True
            if fault == "cancel":
                raise OperationStopped("CANCELLED", "after-preparation-checks")
            return result.model_copy(
                update={
                    "checks": tuple(
                        check.model_copy(update={"evidence": check.evidence + (extra,)})
                        for check in result.checks
                    )
                }
            )

    c.adapter.checks = BodyChecks()
    before = c.authority.calls
    if fault == "extra_dependency":
        _, receipt = c.adapter._verify(c.selection, c.request.operation, guard())
        assert receipt.checks.status == "pass" and calls.count(extra) == 1
        assert c.authority.calls == before + 1
    else:
        expected = PermissionError if fault == "authority_revoked" else OperationStopped
        with pytest.raises(expected):
            c.adapter._verify(c.selection, c.request.operation, guard())

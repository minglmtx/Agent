"""Actual source producers reuse internal preparation work and keep live gates."""

from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.bootstrap.source_qualification_records import (
    SourceQualificationRecords,
)
from lab_generate_skill.bootstrap.map_source_qualification import (
    qualify_map_navigation_source,
    MapSourceQualificationUnconfirmed,
)
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    OperationStopped,
)
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from test_map_source_qualification import source_case as source_case
from test_map_source_qualification import (
    test_source_initializer_unique_initial_observation_restore_reset_and_close_before_publication as map_original,
)
from test_admin_navigation_source_composition import original_source_unit_case
from test_admin_navigation_input import contracts as contracts
from site_instance_fixtures import node_path as node_path
from map_navigation_source_fixtures import selection
import lab_generate_skill.bootstrap.map_source_qualification as map_module


@pytest.mark.parametrize("site", ["map", "admin"])
def test_source_producer_uses_one_preparation_graph_and_check_then_original_reset(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    site: str,
) -> None:
    held: list[SourceQualificationRecords] = []
    actions: list[str] = []
    reads: Counter[int] = Counter()
    checks: Counter[int] = Counter()
    original_define = SourceQualificationRecords.define
    original_request = SourceQualificationRecords.request
    original_read = EvidencePreparationRecords._read_inputs

    def define(records: SourceQualificationRecords, *args: Any, **kwargs: Any) -> Any:
        value = original_define(records, *args, **kwargs)
        held.append(records)
        assert records.records is not None and records.input_bodies is not None
        assert records.records.record_inputs is records.input_bodies.records
        checker = records.records.checks
        original_check = getattr(checker, "check_with_bodies")

        def checked(*a: Any, **kw: Any) -> Any:
            checks[id(records)] += 1
            assert (
                checks[id(records)] == 1
            ), "Reused source preparation check executed again"
            return original_check(*a, **kw)

        monkeypatch.setattr(checker, "check_with_bodies", checked)
        return value

    def read(records: EvidencePreparationRecords, *args: Any, **kwargs: Any) -> Any:
        if records.record_inputs is not None:
            reads[id(records)] += 1
            assert reads[id(records)] == 1, "Reused source graph physically reread"
        return original_read(records, *args, **kwargs)

    def task(
        records: SourceQualificationRecords, action: str, *args: Any, **kwargs: Any
    ) -> Any:
        actions.append(action)
        return original_request(records, action, *args, **kwargs)

    monkeypatch.setattr(SourceQualificationRecords, "define", define)
    monkeypatch.setattr(SourceQualificationRecords, "request", task)
    monkeypatch.setattr(EvidencePreparationRecords, "_read_inputs", read)
    if site == "map":
        map_original(request.getfixturevalue("source_case"), monkeypatch, False, False)
    else:
        original_source_unit_case(
            tmp_path,
            node_path,
            monkeypatch,
            request.getfixturevalue("contracts"),
            "none",
        )
    assert actions == ["snapshot", "prepare", "restore"]
    assert len(held) == 1
    records = held[0]
    assert records.input_bodies is not None and records.records is not None
    facts = records.progress.input_reuse
    assert (
        facts["preparation_graph_reads"]
        == facts["publication_reads"]
        == facts["checks_executed"]
        == 1
    )
    assert facts["preparation_graph_reuses"] > 0 and facts["checks_reused"] > 0
    assert reads[id(records.records)] == checks[id(records)] == 1
    assert not records.input_bodies.active
    assert (
        records.input_bodies.records.graph is None
        and records.input_bodies.records.publication is None
    )
    assert records.input_bodies.prepared_browser is None
    assert (
        records.progress.reset is not None and records.progress.reset.status == "safe"
    )


@pytest.mark.parametrize(
    "fault", ["none", "scope", "body", "publication", "revoked", "cancel"]
)
def test_source_reuse_refuses_changed_facts_and_keeps_original_site_close(
    source_case: Any,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    c, owner, assets = source_case
    assert isinstance(c.private, NavigationSpec)
    seen: list[SourceQualificationRecords] = []

    def measured(
        records: SourceQualificationRecords, *args: Any, **kwargs: Any
    ) -> None:
        seen.append(records)
        assert records.records is not None and records.input_bodies is not None
        p = records.progress
        assert p.publication is not None and p.prepare_request is not None
        operation = p.prepare_request.operation.cleanup(
            "source-reuse-read", now=records.clock.utcnow(), seconds=30
        )
        if fault == "scope":
            operation = operation.model_copy(update={"attempt_id": "foreign-attempt"})
        elif fault == "body":
            held = records.input_bodies.records.graph
            assert held is not None
            records.input_bodies.records.graph = replace(held, private_spec=b"changed")
        elif fault == "publication":
            p.publication = p.publication.model_copy(
                update={
                    "prepared_ref": p.publication.prepared_ref.model_copy(
                        update={"producer": "foreign"}
                    )
                }
            )
        elif fault in {"revoked", "cancel"}:

            def refuse(*args: Any, **kwargs: Any) -> None:
                if fault == "revoked":
                    raise OwnershipConflict("Current source permission revoked")
                raise OperationStopped("CANCELLED", operation.operation_id)

            monkeypatch.setattr(records.input_bodies, "check_context_current", refuse)
        records.records.load(p.publication, operation)
        raise PermissionError("Explicit source-prefix-only stop before browser effects")

    monkeypatch.setattr(map_module, "measure_map_source", measured)
    with pytest.raises(MapSourceQualificationUnconfirmed) as failed:
        qualify_map_navigation_source(
            owner,
            c.resource.spec,
            c.resource.op,
            selection("125732d3658ab4daee02"),
            c.private,
            assets,
            journal=c.resource.journal,
            controls=c.resource.controls,
            clock=c.resource.clock,
            prefix="source-prefix-unit",
            metadata_seconds=120,
        )
    assert len(seen) == 1 and failed.value.cleanup_errors == ()
    expected = (
        PermissionError
        if fault == "none"
        else (
            EvidenceIntegrityError
            if fault == "body"
            else OperationStopped if fault == "cancel" else OwnershipConflict
        )
    )
    assert isinstance(failed.value.primary, expected)
    records = seen[0]
    assert records.input_bodies is not None and not records.input_bodies.active
    assert records.input_bodies.records.graph is None
    read = c.resource.op.cleanup(
        "source-prefix-final-read", now=c.resource.clock.utcnow(), seconds=30
    )
    assert c.resource.journal.read(c.resource.spec.token, read).state == "closed"
    assert (
        failed.value.progress.browser is None
        and not failed.value.actual_actor_dispatched
    )

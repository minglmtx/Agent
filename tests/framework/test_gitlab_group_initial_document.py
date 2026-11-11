"""Use the actual original observation title, without a fabricated HTTP status."""

from pathlib import Path
from lab_generate_skill.domain.observation import ObservationArtifact
from lab_generate_skill.domain.evidence import EvidenceMetadata
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.bootstrap.gitlab_group_records import group_initial_observations
from gitlab_group_prepared_browser_fixtures import joined
from browser_worker_fixtures import UnitBrowser
from initial_observation_fixtures import Authority
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "title,text,expected",
    [
        ("New group", "Page", "pass"),
        ("Not found group", "Page", "pass"),
        ("", "Page", "pass"),
        ("Page not found", "Page", "fail"),
        ("404: Page not found · GitLab", "Page", "fail"),
        ("NOT FOUND", "Page", "fail"),
        ("New group", None, "fail"),
        ("New group", "", "fail"),
        ("New group", " \n\t", "fail"),
    ],
)
def test_original_group_initial_document_title_is_checked_without_reobserve(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    title: str,
    text: str | None,
    expected: str,
) -> None:
    artifacts: tuple[ObservationArtifact, ...] = ()

    class DocumentBrowser(UnitBrowser):
        def value(
            self, op: OperationContext, action: BrowserAction | None
        ) -> BrowserReadout:
            original = super().value(op, action)
            view = original.observation.model_copy(
                update={
                    "tabs": (
                        original.observation.tabs[0].model_copy(
                            update={"title": title}
                        ),
                    ),
                    "text": text,
                    "artifacts": artifacts,
                }
            )
            self.last_readout = original.model_copy(update={"observation": view})
            return self.last_readout

    # This replaces only the explicitly synthetic test engine, never production.
    monkeypatch.setattr("browser_resource_fixtures.UnitBrowser", DocumentBrowser)
    with joined(tmp_path, node_path, monkeypatch) as c:
        b, p = c.browser, c.preparation
        if text is None:
            ref = p.store.put(
                b"controlled textless artifact",
                EvidenceMetadata(
                    media_type="application/octet-stream",
                    content_schema="controlled-observation-artifact/1",
                    visibility="public",
                    producer="explicit-observation-fixture",
                ),
                guard(),
            )
            artifacts = (
                ObservationArtifact(name="controlled-artifact", reference=ref),
            )
        calls = len(p.native.sql.calls)
        with registered_browser(
            b.spec,
            b.op,
            journal=b.journal,
            evidence=b.evidence,
            controls=b.controls,
            clock=b.clock,
            authority=c.authority,
        ) as session:
            assert session.resource_started_ref is not None
            record = b.journal.read(b.spec.token, b.op)
            intent = ResourceAcquisitionIntent.model_validate_json(
                b.evidence.read(record.events[1].evidence[0], guard())
            )
            selected = InitialObservationSelection(
                preparation=c.binding.publication,
                browser_spec_ref=intent.configuration_ref,
                browser_acquired_ref=session.resource_started_ref,
            )
            records = group_initial_observations(
                p.store, b.controls, p.records, Authority(selected)
            )
            op = p.inputs.request.operation.model_copy(
                update={"operation_id": "initial-title"}
            )
            reference = records.publish(selected, op)
            result = records.load(selected, reference, op)
            assert result.checks.status == expected
            assert (
                b.channels[0].engine.calls == ["start"]
                and len(p.native.sql.calls) == calls
            )
        assert b.channels[0].engine.calls == ["start", "close"]

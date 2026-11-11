"""Original Group preparation -> common binding -> one seq0 -> closed graph."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.browser_initialization import (
    PublicNavigation,
    BrowserInitialization,
)
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabGroupInitialization,
)
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceError
from lab_generate_skill.bootstrap.gitlab_group_records import group_initial_observations
from gitlab_group_prepared_browser_fixtures import joined
from initial_observation_fixtures import Authority
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "account",
        "checker-missing",
        "wrong-kind",
        "prepared",
        "closed-site",
        "site-writer",
    ],
)
def test_group_original_records_join_common_binding_and_unique_initial(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with joined(tmp_path, node_path, monkeypatch) as c:
        b, p = c.browser, c.preparation
        calls = len(p.native.sql.calls)
        if fault != "none":
            selected: BrowserInitialization = b.spec.configuration.initialization
            assert isinstance(selected, GitlabGroupInitialization)
            if fault == "account":
                selected = selected.model_copy(update={"native_account_id": 2})
            elif fault == "checker-missing":
                c.binding.task_checks = None
            elif fault == "wrong-kind":
                selected = PublicNavigation()
            elif fault == "prepared":
                selected = selected.model_copy(
                    update={
                        "prepared_ref": selected.prepared_ref.model_copy(
                            update={"producer": "foreign"}
                        )
                    }
                )
            elif fault == "closed-site":
                journal = c.binding.journal
                old = journal.read(c.binding.site_spec.token, c.binding.site_operation)
                op = c.binding.site_operation.cleanup(
                    "site-close", now=b.clock.utcnow(), seconds=20
                )
                journal.advance(
                    old.token, "closing", old.events[-1].evidence, old.revision, op
                )
            elif fault == "site-writer":
                slurm = c.binding.site_spec.slurm
                bad = slurm.parent.writer.model_copy(
                    update={"start_ticks": slurm.parent.writer.start_ticks + 1}
                )
                c.binding.site_spec = c.binding.site_spec.model_copy(
                    update={
                        "slurm": slurm.model_copy(
                            update={
                                "parent": slurm.parent.model_copy(
                                    update={"writer": bad}
                                )
                            }
                        )
                    }
                )
            b.spec = b.spec.model_copy(
                update={
                    "configuration": b.spec.configuration.model_copy(
                        update={"initialization": selected}
                    )
                }
            )
            with pytest.raises((ValueError, OwnershipConflict, EvidenceError)):
                c.binding.verify(b.spec, b.op, guard())
            assert not b.channels and len(p.native.sql.calls) == calls
            return
        # Binding authority is used by the actual public resource entry below.
        with registered_browser(
            b.spec,
            b.op,
            journal=b.journal,
            evidence=b.evidence,
            controls=b.controls,
            clock=b.clock,
            authority=c.authority,
        ) as session:
            assert (
                session.observation_ref is not None
                and session.resource_started_ref is not None
            )
            observation = Observation.model_validate_json(
                b.evidence.read(session.observation_ref, guard())
            )
            assert (
                observation.sequence == 0
                and observation.tabs[0].url == p.inputs.public_task.start_url
            )
            record = b.journal.read(b.spec.token, b.op)
            intent = ResourceAcquisitionIntent.model_validate_json(
                b.evidence.read(record.events[1].evidence[0], guard())
            )
            initial_selection = InitialObservationSelection(
                preparation=c.binding.publication,
                browser_spec_ref=intent.configuration_ref,
                browser_acquired_ref=session.resource_started_ref,
            )
            authority = Authority(initial_selection)
            records = group_initial_observations(
                p.store, b.controls, p.records, authority
            )
            op = p.inputs.request.operation.model_copy(
                update={"operation_id": "group-initial-check"}
            )
            reference = records.publish(initial_selection, op)
            initial = records.load(initial_selection, reference, op)
            assert (
                initial.checks.status == "pass"
                and records.load(initial_selection, reference, op) == initial
            )
            assert observation.sequence == 0 and len(p.native.sql.calls) == calls
            assert len(b.channels) == 1 and b.channels[0].engine.calls == ["start"]
        closed = b.journal.read(
            b.spec.token,
            b.op.cleanup("browser-closed-read", now=b.clock.utcnow(), seconds=20),
        )
        assert closed.state == "closed" and len(p.native.sql.calls) == calls
        assert (
            c.binding.journal.read(
                c.binding.site_spec.token, c.binding.site_operation
            ).state
            == "acquired"
        )

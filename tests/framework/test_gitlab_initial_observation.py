"""Selected original record graph and one fake browser return; no real-site claim."""

import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_initialization import PublicNavigation
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabSshKeyInitialization,
)
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.preparation import PreparationReceipt
from lab_generate_skill.domain.baseline import BaselineInputs, assemble_baseline
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.bootstrap.gitlab_ssh_records import gitlab_initial_observations
from lab_generate_skill.bootstrap.gitlab_ssh_records import (
    gitlab_prepared_browser_checks,
)
from lab_generate_skill.bootstrap.gitlab_ssh_records import gitlab_state_qualifications
from gitlab_qualification_fixtures import qualified, restore
from gitlab_preparation_fixtures import put
from browser_resource_fixtures import resource_case
from browser_worker_fixtures import configuration
from initial_observation_fixtures import Authority
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("fault", ["none", "wrong_prepared", "wrong_kind"])
def test_original_selected_publication_and_one_observation_ready_baseline(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    native_shutdown: bool = False,
) -> None:
    with qualified(tmp_path, node_path, native_shutdown=native_shutdown) as c:
        p, store = c.preparation, c.preparation.store
        publication = p.records.publish(p.inputs.selection, p.inputs.request.operation)
        prepared = p.records.load(publication, p.inputs.request.operation)
        base = configuration(p.configuration.installation)
        session_spec = BrowserSessionSpec.model_validate(
            {
                **base.spec.model_dump(),
                "scope": prepared.scope,
                "task": prepared.public_task,
            }
        )
        selected = GitlabSshKeyInitialization(
            endpoint=c.started.instance.endpoint,
            native_account_id=p.native.reader.value.account.id,
            prepared_ref=publication.prepared_ref,
            site_ref=put(store, c.started),
        )
        gitlab_prepared_browser_checks(store).check(
            publication, c.site, c.started, p.inputs.request, selected, guard()
        )
        if fault == "wrong_prepared":
            selected = selected.model_copy(
                update={
                    "prepared_ref": selected.prepared_ref.model_copy(
                        update={"producer": "foreign"}
                    )
                }
            )
        config = BrowserWorkerConfiguration.model_validate(
            {
                **base.model_dump(),
                "spec": session_spec,
                "initialization": (
                    PublicNavigation() if fault == "wrong_kind" else selected
                ),
            }
        )
        root = tmp_path / "browser"
        root.mkdir()
        b = resource_case(root, monkeypatch, config=config, store=store)
        before = p.native.reader.calls
        with registered_browser(
            b.spec,
            b.op,
            journal=b.journal,
            evidence=store,
            controls=b.controls,
            clock=b.clock,
            authority=b.authority,
        ) as session:
            assert session.observation_ref is not None
            record = b.journal.read(b.spec.token, b.op)
            intent = ResourceAcquisitionIntent.model_validate_json(
                store.read(record.events[1].evidence[0])
            )
            assert session.resource_started_ref is not None
            selection = InitialObservationSelection(
                preparation=publication,
                browser_spec_ref=intent.configuration_ref,
                browser_acquired_ref=session.resource_started_ref,
            )
            authority = Authority(selection)
            records = gitlab_initial_observations(
                store, b.controls, p.records, authority
            )
            op = p.inputs.request.operation.model_copy(
                update={"operation_id": "selected-initial-checks"}
            )
            if fault == "none":
                ref = records.publish(selection, op)
                initial = records.load(selection, ref, op)
                observation = Observation.model_validate_json(
                    store.read(session.observation_ref)
                )
                preparation = PreparationReceipt.model_validate_json(
                    store.read(publication.preparation_ref)
                )
                inputs = BaselineInputs(
                    binding=p.inputs.binding,
                    public_task=p.inputs.public_task,
                    spec=p.inputs.spec,
                    spec_ref=p.inputs.binding.baseline_ref,
                    environment=p.inputs.environment,
                    environment_ref=p.inputs.selection.environment_ref,
                    preparation=preparation,
                    preparation_ref=publication.preparation_ref,
                    prepared=prepared,
                    prepared_ref=publication.prepared_ref,
                    observation=observation,
                    observation_ref=session.observation_ref,
                    initial=initial,
                    initial_ref=ref,
                )
                baseline = assemble_baseline(
                    inputs, op.model_copy(update={"operation_id": "selected-baseline"})
                )
                assert (
                    baseline.status == "ready"
                    and observation.sequence == 0
                    and initial.checks.status == "pass"
                )
                assert records.load(selection, ref, op) == initial
                authority.denied = True
                with pytest.raises(PermissionError):
                    records.load(selection, ref, op)
            else:
                with pytest.raises((ValueError, OwnershipConflict)):
                    records.publish(selection, op)
            assert b.channels[0].engine.calls == ["start"]
            assert p.native.reader.calls == before
        record = b.journal.read(b.spec.token, b.op)
        assert record.state == "closed"
        ending = json.loads(store.read(record.events[-1].evidence[0]))
        closure = ClosureReceipt.model_validate_json(
            json.dumps(ending["details"]["closure"])
        )
        assert closure.status == "closed" and closure.token == b.spec.token
        if fault == "none":
            reset_selection = restore(c, (b.spec.token,), (put(store, closure),))
            checks = gitlab_state_qualifications(store, b.controls, c.authority)
            reset_op = p.inputs.request.operation.cleanup(
                "combined-reset-records", now=datetime.now(timezone.utc), seconds=30
            ).model_copy(update={"recovery_ref": c.site.token.recovery_ref})
            reset = checks.publish_reset_facts(put(store, reset_selection), reset_op)
            assert (
                reset.task.checks.status
                == reset.environment.checks.status
                == reset.health.checks.status
                == "pass"
            )
            assert len(p.native.task.instance.generations) == 3
            if native_shutdown:
                assert p.native.task.snapshot is not None
                assert len(p.native.task.snapshot.state.workhorse_terms) == 2
                assert p.native.task.snapshot.state.gitaly_term is None
                from lab_generate_skill.sites.gitlab.tasks.ssh_key_recovery import (
                    SshKeyRestored,
                )

                assert p.native.task.restore_result is not None
                returned = SshKeyRestored.model_validate_json(
                    p.native.task.restore_result.private_result
                )
                assert (
                    returned.gitaly_term is None and len(returned.workhorse_terms) == 2
                )
                assert len(returned.model_dump_json().encode()) < 1024 * 1024
            assert b.channels[0].engine.calls == ["start", "close"]
            from lab_generate_skill.domain.reset import ResetInputs
            from lab_generate_skill.sites.gitlab.tasks.ssh_key_state_checks import (
                SshKeyStateChecks,
            )
            from lab_generate_skill.bootstrap.gitlab_ssh_state import load_ssh_key_state
            from gitlab_actor_review import review_gitlab_reset
            from source_review_records import ReadOnlyEvidence

            reset_ref = put(store, reset_selection)
            expected = SshKeyStateChecks(store, load_ssh_key_state).reset(
                reset_selection, reset_ref, guard()
            )
            reset_inputs = ResetInputs(
                plan=expected.plan,
                plan_ref=reset_selection.plan_ref,
                spec=expected.spec,
                task_recovery=expected.task_recovery,
                environment_recovery=expected.environment_recovery,
                closures=expected.closures,
                closure_refs=reset_selection.closure_refs,
                task=reset.task,
                task_ref=reset.task_ref,
                environment=reset.environment,
                environment_ref=reset.environment_ref,
                health=reset.health,
                health_ref=reset.health_ref,
            )
            original = {
                "qualified_source": {
                    "reset_selection_ref": reset_ref.model_dump(mode="json")
                }
            }
            readonly = ReadOnlyEvidence(node_path / "private-evidence")
            review_gitlab_reset(original, reset_inputs, readonly, guard())
            review_gitlab_reset(original, reset_inputs, readonly, guard())
            from lab_generate_skill.domain.errors import EvidenceIntegrityError

            with pytest.raises(EvidenceIntegrityError, match="full reset differs"):
                review_gitlab_reset(
                    original,
                    reset_inputs.model_copy(
                        update={
                            "health": reset.health.model_copy(
                                update={"checks": expected.task}
                            )
                        }
                    ),
                    readonly,
                    guard(),
                )


def test_native_term_proofs_survive_original_ready_and_independent_full_reset(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_original_selected_publication_and_one_observation_ready_baseline(
        tmp_path, node_path, monkeypatch, "none", native_shutdown=True
    )

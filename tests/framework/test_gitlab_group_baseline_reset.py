"""One frozen Group graph through ready baseline, closure, restore and safe reset.

Real CAS/journals/tree copies; SQL/services/kernel/browser are explicit doubles.
No benchmark website, original source execution, Actor or training admission.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.plans.reset_evidence import ResetEvidenceReader
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.preparation import PreparationReceipt
from lab_generate_skill.domain.baseline import BaselineInputs, assemble_baseline
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.reset import ResetInputs, assemble_reset
from lab_generate_skill.domain.errors import OwnershipConflict, OperationStopped
from lab_generate_skill.sites.gitlab.tasks.group_state_checks import GroupStateChecks
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from lab_generate_skill.bootstrap.gitlab_group_records import (
    group_initial_observations,
    group_state_qualifications,
)
from gitlab_group_prepared_browser_fixtures import joined
from gitlab_group_qualification_fixtures import restore
from gitlab_group_preparation_fixtures import put
from gitlab_group_fixtures import native_state
from initial_observation_fixtures import Authority
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path
from source_review_records import ReadOnlyEvidence
from lab_generate_skill.bootstrap.gitlab_group_evaluation import gitlab_group_evaluator
from gitlab_group_evaluator_fixtures import capture_pair, evaluation_selection
from gitlab_group_review_process import closed_group_review
from synthetic_browser_trace import one_return


def test_original_group_ready_baseline_then_closed_full_tree_restore_resume_safe_reset(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with joined(tmp_path, node_path, monkeypatch) as c:
        b, p = c.browser, c.preparation
        qualified = c.qualified
        publication = c.binding.publication
        prepared = p.records.load(publication, p.inputs.request.operation)
        read_calls = len(p.native.sql.calls)
        original_group = (p.native.state / "group.json").read_bytes()
        original_projects = (p.native.state / "projects.csv").read_bytes()
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
            record = b.journal.read(b.spec.token, b.op)
            intent = ResourceAcquisitionIntent.model_validate_json(
                p.store.read(record.events[1].evidence[0], guard())
            )
            selection = InitialObservationSelection(
                preparation=publication,
                browser_spec_ref=intent.configuration_ref,
                browser_acquired_ref=session.resource_started_ref,
            )
            initial_records = group_initial_observations(
                p.store, b.controls, p.records, Authority(selection)
            )
            op = p.inputs.request.operation.model_copy(
                update={"operation_id": "group-baseline-initial"}
            )
            initial_ref = initial_records.publish(selection, op)
            initial = initial_records.load(selection, initial_ref, op)
            observation = Observation.model_validate_json(
                p.store.read(session.observation_ref, guard())
            )
            receipt = PreparationReceipt.model_validate_json(
                p.store.read(publication.preparation_ref, guard())
            )
            baseline = assemble_baseline(
                BaselineInputs(
                    binding=p.inputs.binding,
                    public_task=p.inputs.public_task,
                    spec=p.inputs.spec,
                    spec_ref=p.inputs.binding.baseline_ref,
                    environment=p.inputs.environment,
                    environment_ref=p.inputs.selection.environment_ref,
                    preparation=receipt,
                    preparation_ref=publication.preparation_ref,
                    prepared=prepared,
                    prepared_ref=publication.prepared_ref,
                    observation=observation,
                    observation_ref=session.observation_ref,
                    initial=initial,
                    initial_ref=initial_ref,
                ),
                op.model_copy(update={"operation_id": "group-ready-baseline"}),
            )
            assert baseline.status == "ready" and observation.sequence == 0
            assert len(p.native.sql.calls) == read_calls and b.channels[
                0
            ].engine.calls == ["start"]
            before = capture_pair(p, "joined-before")
            trace = one_return(
                p.store,
                prepared.public_task,
                prepared.scope,
                b.op,
                initial_ref=session.observation_ref,
            )
            assert trace.initial_observation_ref == session.observation_ref
            # Fixture writes stand in for task effects, never for expected restore.
            (p.native.state / "group.json").write_bytes(
                native_state(inserted=True).model_dump_json().encode()
            )
            (p.native.state / "projects.csv").write_bytes(b"changed original project\n")
            (p.native.state / "non-target-created-file").write_bytes(b"must be removed")
            after = capture_pair(p, "joined-after")
            contract, selected = evaluation_selection(
                qualified, b.spec, trace, before, after
            )
            reads_after_capture = len(p.native.sql.calls)
            evaluation = gitlab_group_evaluator(selected).evaluate(
                contract, p.store, guard()
            )
            assert evaluation.status == "unknown" and evaluation.reward is None
            assert evaluation.reason_code == "PROTECTED_PROJECTS_CHANGED"
            assert len(p.native.sql.calls) == reads_after_capture
        closed = b.journal.read(b.spec.token, b.op)
        assert closed.state == "closed" and b.channels[0].engine.calls == [
            "start",
            "close",
        ]
        ending = json.loads(p.store.read(closed.events[-1].evidence[0], guard()))
        closure = ClosureReceipt.model_validate_json(
            json.dumps(ending["details"]["closure"])
        )
        assert closure.status == "closed" and closure.token == b.spec.token
        review = closed_group_review(
            tmp_path, node_path / "private-evidence", contract, selected, evaluation
        )
        assert review["original_oracle"] == "all_original_conditions_and_guard_equal"
        assert (
            review["state_change_requires_review"] and not review["business_accepted"]
        )
        assert len(p.native.sql.calls) == reads_after_capture
        reset_selection = restore(qualified, (b.spec.token,), (put(p.store, closure),))
        assert (p.native.state / "group.json").read_bytes() == original_group
        assert (p.native.state / "projects.csv").read_bytes() == original_projects
        assert not (p.native.state / "non-target-created-file").exists()
        records = group_state_qualifications(p.store, b.controls, qualified.authority)
        reset_op = p.inputs.request.operation.cleanup(
            "group-reset-records", now=datetime.now(timezone.utc), seconds=30
        ).model_copy(update={"recovery_ref": qualified.site.token.recovery_ref})
        selection_ref = put(p.store, reset_selection)
        facts = records.publish_reset_facts(selection_ref, reset_op)
        expected = GroupStateChecks(p.store, load_group_capture).reset(
            reset_selection, selection_ref, guard()
        )
        inputs = ResetInputs(
            plan=expected.plan,
            plan_ref=reset_selection.plan_ref,
            spec=expected.spec,
            task_recovery=expected.task_recovery,
            environment_recovery=expected.environment_recovery,
            closures=expected.closures,
            closure_refs=reset_selection.closure_refs,
            task=facts.task,
            task_ref=facts.task_ref,
            environment=facts.environment,
            environment_ref=facts.environment_ref,
            health=facts.health,
            health_ref=facts.health_ref,
        )
        final = assemble_reset(
            inputs,
            reset_op.model_copy(
                update={
                    "operation_id": "group-safe-reset",
                    "parent_operation_id": expected.plan.parent_operation_id,
                }
            ),
        )
        assert final.status == "safe" and len(p.native.task.instance.generations) == 3
        reads_after_restore = len(p.native.sql.calls)
        readonly = ReadOnlyEvidence(node_path / "private-evidence")
        assert ResetEvidenceReader(readonly).verify(final, guard()) == inputs
        assert (
            GroupStateChecks(p.store, load_group_capture).reset(
                reset_selection, selection_ref, guard()
            )
            == expected
        )
        assert len(p.native.sql.calls) == reads_after_restore
        uncertain = assemble_reset(
            inputs.model_copy(
                update={
                    "closures": (closure.model_copy(update={"status": "unconfirmed"}),)
                }
            ),
            final.operation,
        )
        assert uncertain.status == "quarantined"
        with pytest.raises(OwnershipConflict):
            assemble_reset(
                inputs.model_copy(update={"closure_refs": ()}), final.operation
            )
        with pytest.raises(OperationStopped):
            GroupStateChecks(p.store, load_group_capture).reset(
                reset_selection, selection_ref, guard(-1)
            )
        assert len(p.native.sql.calls) == reads_after_restore

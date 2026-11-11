"""One registered site -> prepared browser -> ready Baseline -> closed -> safe Reset.

Original wire/CAS/file readers and fixed assemblies; native/Page/kernel/authority
are explicit fixture doubles. This does not claim a live geographic site/Actor.
"""

from datetime import datetime, timezone
import json
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.bootstrap.map_initial_observation import (
    map_initial_observations,
)
from lab_generate_skill.domain.baseline import (
    BaselineInputs,
    BaselineReceipt,
    assemble_baseline,
)
from lab_generate_skill.domain.reset import ResetInputs, ResetReceipt, assemble_reset
from lab_generate_skill.domain.lifecycle import ClosureReceipt, OperationContext
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.preparation import PreparationReceipt
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.errors import OwnershipConflict
from map_qualification_fixtures import qualified, restore
from map_prepared_browser_fixtures import bind
from map_registered_worker_fixtures import RegisteredMapCase
from initial_observation_fixtures import Authority
from preparation_record_fixtures import put
from test_map_browser_collection import capture
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard
from map_prepared_records_fixtures import PreparedMapCase


class StateAuthority:
    """Explicit unit authority; full persisted graphs still verified by production."""

    def __init__(self, original: RegisteredMapCase) -> None:
        self.scope = original.scope

    def verify_baseline(
        self, inputs: BaselineInputs, receipt: BaselineReceipt, op: OperationContext
    ) -> None:
        assert (
            inputs.prepared.scope == receipt.scope == self.scope
            and receipt.operation == op
        )

    def verify_reset(
        self, inputs: ResetInputs, receipt: ResetReceipt, op: OperationContext
    ) -> None:
        assert (
            inputs.plan.scope == receipt.scope == self.scope and receipt.operation == op
        )


@pytest.mark.parametrize("forced", [False, True])
def test_same_entry_ready_baseline_original_browser_closed_and_safe_reset(
    registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch, forced: bool
) -> None:
    original = registered_map
    with qualified(original, monkeypatch, browser=True) as c:
        assert c.browser is not None
        p, store = c.preparation, original.resource.evidence
        assert isinstance(p, PreparedMapCase)
        b, binding, authority = bind(
            original, p, c.live, monkeypatch, browser=c.browser
        )
        assert c.plan.attempt_allocations == (b.resource.spec.token,)
        original.observer = "controller"
        states = EvidenceStateRecords(
            store, original.resource.controls, StateAuthority(original)
        )
        with registered_browser(
            b.resource.spec,
            b.resource.op,
            journal=b.resource.journal,
            evidence=store,
            controls=b.resource.controls,
            clock=b.resource.clock,
            authority=authority,
        ) as browser:
            assert b.engine is not None and b.collector is not None
            first = b.engine.last_readout
            recorder, request = capture(b, browser)
            request = request.model_copy(
                update={
                    "collector_id": "map-initial-readiness",
                    "operation": request.operation.model_copy(
                        update={"operation_id": "initial-native-capture"}
                    ),
                }
            )
            result_ref = recorder.capture(request, control=guard())
            assert recorder.intent_ref is not None
            evidence = MapInitialEvidence(
                intent_ref=recorder.intent_ref, result_ref=result_ref
            )
            record = b.resource.journal.read(b.resource.spec.token, b.resource.op)
            intent = ResourceAcquisitionIntent.model_validate_json(
                store.read(record.events[1].evidence[0])
            )
            assert browser.resource_started_ref is not None
            selection = InitialObservationSelection(
                preparation=p.publication,
                browser_spec_ref=intent.configuration_ref,
                browser_acquired_ref=browser.resource_started_ref,
            )
            initials = map_initial_observations(
                store,
                b.resource.controls,
                p.records,
                Authority(selection),
                evidence,
                initialization=b.configuration.initialization,
            )
            op = p.request.operation.model_copy(
                update={"operation_id": "initial-checks"}
            )
            ref = initials.publish(selection, op)
            initial = initials.load(selection, ref, op)
            selected = initials.reader.load(selection, op, guard())
            task_binding = TaskBinding.model_validate_json(store.read(original.binding))
            preparation = PreparationReceipt.model_validate_json(
                store.read(p.publication.preparation_ref)
            )
            inputs = BaselineInputs(
                binding=task_binding,
                public_task=selected.prepared.public_task,
                spec=selected.spec,
                spec_ref=selected.prepared.spec_ref,
                environment=p.environment,
                environment_ref=p.publication.selection.environment_ref,
                preparation=preparation,
                preparation_ref=p.publication.preparation_ref,
                prepared=selected.prepared,
                prepared_ref=p.publication.prepared_ref,
                observation=selected.returned.observation,
                observation_ref=initial.observation_ref,
                initial=initial,
                initial_ref=ref,
            )
            baseline_op = op.model_copy(update={"operation_id": "baseline"})
            baseline = assemble_baseline(inputs, baseline_op)
            baseline_ref = states.publish_baseline(baseline, baseline_op)
            assert (
                states.load_baseline(baseline_ref, baseline_op) == baseline
                and baseline.status == "ready"
            )
            assert (
                b.engine.last_readout is first
                and selected.returned.observation.sequence == 0
            )
            assert b.calls.count("project") == 1 and b.collector.state == "active"
            terminal, terminal_request = capture(b, browser)
            terminal.capture(terminal_request, control=guard(30))
            assert b.engine.last_readout is first and b.collector.state == "published"
        record = b.resource.journal.read(b.resource.spec.token, b.resource.op)
        assert record.state == "closed"
        ending = json.loads(store.read(record.events[-1].evidence[0]))
        closure = ClosureReceipt.model_validate_json(
            json.dumps(ending["details"]["closure"])
        )
        assert closure.status == "closed" and closure.token == b.resource.spec.token
        closure_ref = put(store, closure)
        selected_reset = restore(c, closure_refs=(closure_ref,), forced=forced)
        reset_op = p.request.operation.cleanup(
            "reset-facts", now=datetime.now(timezone.utc), seconds=30
        ).model_copy(update={"recovery_ref": c.plan.environment_recovery_ref})
        reset_inputs = c.qualifications.publish_reset_facts(
            put(store, selected_reset), reset_op
        )
        final_op = reset_op.model_copy(update={"operation_id": "reset-summary"})
        reset = assemble_reset(reset_inputs, final_op)
        reset_ref = states.publish_reset(reset, final_op)
        assert (
            states.load_reset(reset_ref, final_op) == reset and reset.status == "safe"
        )
        calls = (
            len(original.case.commands.calls),
            len(original.generation.groups),
            len(b.calls),
        )
        assert (
            c.qualifications.checks.reset(
                selected_reset, put(store, selected_reset), guard()
            ).health.status
            == "pass"
        )
        bad = selected_reset.model_copy(
            update={
                "closure_refs": (
                    put(store, closure.model_copy(update={"status": "unconfirmed"})),
                )
            }
        )
        with pytest.raises(OwnershipConflict, match="closed"):
            c.qualifications.publish_reset_facts(put(store, bad), reset_op)
        assert calls == (
            len(original.case.commands.calls),
            len(original.generation.groups),
            len(b.calls),
        )
        assert (
            b.collector is not None
            and b.collector.native is not None
            and b.collector.native.requests.relay.physical_closed
        )
        assert (
            original.worker is not None
            and original.worker.tasks is not None
            and original.worker.tasks.phase == "resumed"
        )
    assert (
        original.resource.journal.read(
            original.resource.spec.token, original.resource.op
        ).state
        == "closed"
    )

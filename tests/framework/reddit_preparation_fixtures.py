"""Actual selected task/CAS/records with synthetic services and environment facts."""

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.preparation_record import (
    PreparationSelection,
    PreparationInputs,
)
from lab_generate_skill.bootstrap.reddit_native_image import load_image_inputs
from lab_generate_skill.bootstrap.reddit_image_records import (
    bind_image_records,
    image_preparation_records,
)
from lab_generate_skill.sites.reddit.tasks.image_policy import (
    image_initial_spec,
    ENVIRONMENT_RESET_CHECKS,
)
from lab_generate_skill.sites.reddit.state_reads import RedditStateReads
from lab_generate_skill.runtime.lifecycle import OperationGuards
from lab_generate_skill.ports.task_bindings import TaskBindings
from reddit_image_lifecycle_fixtures import Case as NativeCase, case
from test_reddit_worker_instance import config as worker_configuration
from lab_generate_skill.bootstrap.reddit_browser_files import WORKSPACE
from preparation_record_fixtures import Authority
from evidence_control_fixtures import EvidenceFixtureStore
from test_reddit_image_inputs import FIXTURE, public_task
from test_resource_journal import NoCancellation
from test_slurm_commands import guard


def metadata(schema: str) -> EvidenceMetadata:
    return EvidenceMetadata(
        media_type="application/json",
        content_schema=schema,
        visibility="private",
        producer="selected-reddit-unit",
    )


def put(store: EvidenceFixtureStore, value: Contract) -> EvidenceRef:
    return store.put(
        value.model_dump_json().encode(),
        metadata(str(value.model_dump()["schema_version"])),
        guard(),
    )


@dataclass
class Case:
    native: NativeCase
    store: EvidenceFixtureStore
    authority: Authority
    bindings: TaskBindings
    records: EvidencePreparationRecords
    inputs: PreparationInputs
    configuration: SiteWorkerConfiguration


@contextmanager
def prepared_case(
    root: Path,
    node: Path,
    *,
    owner_guard: ProcessOwnerGuard | None = None,
) -> Iterator[Case]:
    config = worker_configuration(root, node)
    config = config.model_copy(
        update={"files": config.files.model_copy(update={"workspace_root": WORKSPACE})}
    )
    state_spec = image_initial_spec(public_task().identity)
    spec_ref = evidence_reference(
        state_spec.model_dump_json().encode(), metadata(state_spec.schema_version)
    )
    environment_recovery = RecoveryPlan(
        recovery_id="reddit-environment",
        owner=config.token.owner,
        baseline_ref=spec_ref,
        restore_component_id="reddit-services",
        restore_component_version="1",
        state_coverage=ENVIRONMENT_RESET_CHECKS,
    )
    environment_recovery_ref = evidence_reference(
        environment_recovery.model_dump_json().encode(),
        metadata(environment_recovery.schema_version),
    )
    config = config.model_copy(
        update={
            "token": config.token.model_copy(
                update={"recovery_ref": environment_recovery_ref}
            )
        }
    )
    c = case(
        node,
        configured=config,
        owner_guard=owner_guard,
    )
    try:
        store = c.artifacts.store
        assert put(store, state_spec) == spec_ref
        assert put(store, environment_recovery) == environment_recovery_ref
        public = public_task().model_copy(
            update={"start_url": c.artifacts.context.instance.endpoint + "submit"}
        )
        native_ref = store.put(
            FIXTURE.read_bytes(), metadata("reddit-native-contract/1"), guard()
        )
        private = load_image_inputs(
            FIXTURE.read_bytes(), native_ref, public
        ).private_spec
        public_ref = store.put(
            public.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema=public.schema_version,
                visibility="public",
                producer="selected-reddit-unit",
            ),
            guard(),
        )
        binding = TaskBinding(
            identity=public.identity,
            registration_id="engineering-reddit-image",
            public_task_ref=public_ref,
            private_spec_ref=put(store, private),
            baseline_ref=spec_ref,
        )
        authority = Authority()
        controls = OperationGuards(SystemClock(), NoCancellation())
        bindings = bind_image_records(store, controls, authority)
        binding_ref = bindings.publish(binding, c.request.operation)
        task_recovery = RecoveryPlan(
            recovery_id="reddit-task",
            owner=config.token.owner,
            attempt_id="attempt",
            baseline_ref=spec_ref,
            restore_component_id="reddit-native-image",
            restore_component_version="1",
            state_coverage=state_spec.task_reset_checks,
        )
        recovery_ref = put(store, task_recovery)
        c.request = c.request.model_copy(
            update={
                "binding_ref": binding_ref,
                "private_input": private.model_dump_json(),
                "operation": c.request.operation.model_copy(
                    update={"recovery_ref": recovery_ref}
                ),
            }
        )
        snapshot_result = c.task.execute_task(c.request, control=guard())
        assert c.task.snapshot is not None
        snapshot_ref = put(store, c.task.snapshot)
        assert (
            store.read(snapshot_ref, control=guard())
            == snapshot_result.private_result.encode()
        )
        request = c.next("prepare", "original-prepare", snapshot_ref=snapshot_ref)
        assert request.snapshot_ref == snapshot_ref
        result = c.task.execute_task(request, control=guard())
        environment = EnvironmentBaseline(
            scope=StateScope(
                owner=config.token.owner,
                task=private.task,
                attempt_id="attempt",
                context_id="native-context",
            ),
            operation=c.request.operation.model_copy(
                update={
                    "operation_id": "explicit-synthetic-environment",
                    "recovery_ref": environment_recovery_ref,
                }
            ),
            allocation=config.token,
            spec_ref=spec_ref,
            checks=RedditStateReads.checks(
                state_spec.environment_checks, (spec_ref,), "SYNTHETIC_UNIT_ENVIRONMENT"
            ),
            measured_state_sha256=c.task.snapshot.state.inventory.sha256,
        )
        selection = PreparationSelection(
            request_ref=put(store, request),
            result_ref=put(store, result),
            environment_ref=put(store, environment),
        )
        inputs = PreparationInputs(
            selection=selection,
            request=request,
            result=result,
            binding=binding,
            public_task=public,
            spec=state_spec,
            environment=environment,
            recovery=task_recovery,
        )
        records = image_preparation_records(store, controls, bindings, authority)
        yield Case(c, store, authority, bindings, records, inputs, config)
    finally:
        c.task.instance.stop(guard())

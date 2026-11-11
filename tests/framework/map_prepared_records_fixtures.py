"""Original registered Map worker/files and real preparation CAS; native/OS doubles."""

from dataclasses import dataclass
from collections.abc import Callable
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.bootstrap.map_overlay_records import map_preparation_records
from lab_generate_skill.domain.preparation_record import (
    PreparationSelection,
    PreparedPublication,
)
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.sites.map.tasks.overlay_policy import overlay_initial_spec
from lab_generate_skill.sites.map.tasks.overlay_recovery import (
    OverlaySnapshot,
    OverlayObserved,
)
from lab_generate_skill.adapters.sites.resource import RegisteredSite
from map_registered_worker_fixtures import RegisteredMapCase
from map_browser_initialization_fixtures import public_task
from preparation_record_fixtures import Authority, put
from test_slurm_commands import guard


@dataclass
class PreparedMapCase:
    request: SiteTaskRequest
    result: SiteTaskResult
    snapshot: OverlaySnapshot
    observed: OverlayObserved
    environment: EnvironmentBaseline
    records: EvidencePreparationRecords
    publication: PreparedPublication


def prepare(
    c: RegisteredMapCase,
    registered: RegisteredSite,
    *,
    environment: Callable[[OverlaySnapshot], EnvironmentBaseline] | None = None,
) -> PreparedMapCase:
    store = c.resource.evidence
    spec = overlay_initial_spec(c.scope.task)
    spec_ref = put(store, spec)
    binding = TaskBinding(
        identity=c.scope.task,
        registration_id="map-native-route-overlay",
        public_task_ref=put(
            store, public_task(registered.site.instance.endpoint), "public"
        ),
        private_spec_ref=put(store, c.private),
        baseline_ref=spec_ref,
    )
    c.binding = put(store, binding)
    c.task_recovery = put(
        store,
        RecoveryPlan(
            recovery_id="original-map-recovery",
            owner=c.scope.owner,
            attempt_id=c.scope.attempt_id,
            baseline_ref=spec_ref,
            restore_component_id="map-native-overlay",
            restore_component_version="1",
            state_coverage=spec.task_reset_checks,
        ),
    )
    saved = registered.tasks.execute_task(c.request("snapshot"), control=guard())
    snapshot = OverlaySnapshot.model_validate_json(saved.private_result)
    c.snapshot_ref = c.put(saved.private_result.encode(), "map-overlay-snapshot/1")
    qualified = environment(snapshot) if environment is not None else None
    request = c.request("prepare")
    result = registered.tasks.execute_task(request, control=guard())
    observed = OverlayObserved.model_validate_json(result.private_result)
    env = (
        qualified
        if qualified is not None
        else EnvironmentBaseline(
            scope=c.scope,
            operation=request.operation.model_copy(
                update={
                    "operation_id": "environment",
                    "recovery_ref": c.configuration.token.recovery_ref,
                }
            ),
            allocation=c.configuration.token,
            spec_ref=spec_ref,
            checks=StateChecks(required=spec.environment_checks),
            measured_state_sha256=snapshot.native.state_sha256,
        )
    )
    selection = PreparationSelection(
        request_ref=put(store, request),
        result_ref=put(store, result),
        environment_ref=put(store, env),
    )
    authority = Authority()
    records = map_preparation_records(
        store,
        c.resource.controls,
        EvidenceTaskBindings(store, c.resource.controls, authority),
        authority,
        c.configuration,
        registered.site.instance,
    )
    c.observer = "controller"
    try:
        publication = records.publish(selection, request.operation)
        records.load(publication, request.operation)
    finally:
        c.observer = "worker"
    return PreparedMapCase(
        request, result, snapshot, observed, env, records, publication
    )

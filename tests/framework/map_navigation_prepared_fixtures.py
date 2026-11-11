"""Navigation8 registered Task/real files/CAS; explicit unit native/phase facts."""

from dataclasses import dataclass
from collections.abc import Callable
from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.adapters.sites.resource import RegisteredSite
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
from lab_generate_skill.sites.map.tasks.navigation_policy import navigation_initial_spec
from lab_generate_skill.sites.map.tasks.navigation_recovery import (
    NavigationSnapshot,
    NavigationObserved,
)
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from map_registered_worker_fixtures import RegisteredMapCase
from map_navigation_fixtures import navigation_case
from preparation_record_fixtures import Authority, put
from test_slurm_commands import guard


@dataclass
class NavigationPreparedCase:
    request: SiteTaskRequest
    result: SiteTaskResult
    snapshot: NavigationSnapshot
    observed: NavigationObserved
    environment: EnvironmentBaseline
    records: EvidencePreparationRecords
    publication: PreparedPublication


def prepare_navigation(
    c: RegisteredMapCase,
    live: RegisteredSite,
    *,
    environment: Callable[[NavigationSnapshot], EnvironmentBaseline] | None = None,
) -> NavigationPreparedCase:
    assert isinstance(c.private, NavigationSpec)
    store = c.resource.evidence
    spec = navigation_initial_spec(c.scope.task, c.private.native_contract_ref.sha256)
    spec_ref = put(store, spec)
    public = navigation_case(c.scope.task.source_task_id).public.model_copy(
        update={
            "start_url": live.site.instance.endpoint.rstrip("/")
            + c.private.original_start_path
        }
    )
    c.binding = put(
        store,
        TaskBinding(
            identity=c.scope.task,
            registration_id="unit-navigation8-original-binding",
            public_task_ref=put(store, public, "public"),
            private_spec_ref=put(store, c.private),
            baseline_ref=spec_ref,
        ),
    )
    c.task_recovery = put(
        store,
        RecoveryPlan(
            recovery_id="unit-navigation8-original-recovery",
            owner=c.scope.owner,
            attempt_id=c.scope.attempt_id,
            baseline_ref=spec_ref,
            restore_component_id="map-native-navigation",
            restore_component_version="1",
            state_coverage=spec.task_reset_checks,
        ),
    )
    saved = live.tasks.execute_task(c.request("snapshot"), control=guard())
    snapshot = NavigationSnapshot.model_validate_json(saved.private_result)
    c.snapshot_ref = c.put(saved.private_result.encode(), "map-navigation-snapshot/1")
    qualified = environment(snapshot) if environment is not None else None
    request = c.request("prepare")
    result = live.tasks.execute_task(request, control=guard())
    observed = NavigationObserved.model_validate_json(result.private_result)
    # No fabricated environment-ready/initial/Reset qualification. These checks
    # remain unknown until the next concrete consumers provide actual facts.
    env = (
        qualified
        if qualified is not None
        else EnvironmentBaseline(
            scope=c.scope,
            operation=request.operation.model_copy(
                update={
                    "operation_id": "unit-navigation8-environment",
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
        live.site.instance,
    )
    c.observer = "controller"
    try:
        publication = records.publish(selection, request.operation)
        records.load(publication, request.operation)
    finally:
        c.observer = "worker"
    return NavigationPreparedCase(
        request, result, snapshot, observed, env, records, publication
    )

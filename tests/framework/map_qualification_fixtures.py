"""Original registered Map facts/files; native, kernel and authority are explicit doubles."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import pytest
from lab_generate_skill.adapters.sites.resource import RegisteredSite
from lab_generate_skill.adapters.sites.recorded_resume import RecordedSiteResume
from lab_generate_skill.adapters.storage.state_qualifications import (
    EvidenceStateQualifications,
)
from lab_generate_skill.bootstrap.map_state_qualification import (
    map_state_qualifications,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    ClosureReceipt,
    RecoveryPlan,
)
from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.reset import ResetPlan
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.state_policy import map_initial_spec
from lab_generate_skill.sites.map.tasks.overlay_recovery import OverlaySnapshot
from lab_generate_skill.sites.map.tasks.navigation_recovery import NavigationSnapshot
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from map_registered_worker_fixtures import RegisteredMapCase, NativeGroup
from map_prepared_records_fixtures import prepare, PreparedMapCase
from map_navigation_prepared_fixtures import prepare_navigation, NavigationPreparedCase
from map_browser_collection_fixtures import CollectionCase
from gitlab_qualification_fixtures import Authority
from preparation_record_fixtures import put
from site_resume_fixtures import Authority as ResumeAuthority
from test_site_resource import enter
from test_slurm_commands import guard


@dataclass
class QualifiedMapCase:
    original: RegisteredMapCase
    live: RegisteredSite
    preparation: PreparedMapCase | NavigationPreparedCase
    environment: EnvironmentSelection
    environment_ref: EvidenceRef
    qualifications: EvidenceStateQualifications
    authority: Authority
    plan: ResetPlan
    plan_ref: EvidenceRef
    browser: CollectionCase | None


def configure_qualification(
    c: RegisteredMapCase, patch: pytest.MonkeyPatch
) -> tuple[EvidenceRef, AllocationToken]:
    store = c.resource.evidence
    spec = map_initial_spec(c.scope.task, c.private.native_contract_ref.sha256)
    spec_ref = put(store, spec)
    recovery = RecoveryPlan(
        recovery_id="map-environment",
        owner=c.scope.owner,
        baseline_ref=spec_ref,
        restore_component_id="map-services",
        restore_component_version="1",
        state_coverage=spec.environment_reset_checks,
    )
    token = c.configuration.token.model_copy(
        update={"recovery_ref": put(store, recovery)}
    )
    c.configuration = c.configuration.model_copy(update={"token": token})
    c.resource.spec = c.resource.spec.model_copy(
        update={"configuration": c.configuration}
    )
    c.resource.op = c.resource.op.model_copy(
        update={"recovery_ref": token.recovery_ref}
    )

    # Preserve synthetic PIDs/inodes, but explicitly bind native namespace host/order
    # to this fixture's original worker; do not relax production identity checks.
    original_pin = NativeGroup.pin_namespace

    def pin(
        group: NativeGroup, name: str, control: OperationControl
    ) -> NativeNamespaceIdentity:
        old = original_pin(group, name, control)
        worker = c.owner_guard.worker
        identities = tuple(
            p.model_copy(
                update={
                    "node_id": worker.node_id,
                    "boot_id": worker.boot_id,
                    "start_ticks": worker.start_ticks + 100 + group.generation * 2 + i,
                }
            )
            for i, p in enumerate((old.launcher, old.init))
        )
        value = old.model_copy(
            update={"launcher": identities[0], "init": identities[1]}
        )
        group.pins[-1] = value
        return value

    patch.setattr(NativeGroup, "pin_namespace", pin)
    return spec_ref, token


@contextmanager
def qualified(
    c: RegisteredMapCase, patch: pytest.MonkeyPatch, *, browser: bool = False
) -> Iterator[QualifiedMapCase]:
    store = c.resource.evidence
    if browser and isinstance(c.private, NavigationSpec):
        raise ValueError(
            "Navigation requires its explicit browser initialization consumer"
        )
    spec_ref, token = configure_qualification(c, patch)
    b: CollectionCase | None = None
    if browser:
        root = c.workspace / "browser"
        root.mkdir(mode=0o700)
        b = CollectionCase(
            root, patch, owner=c.scope.owner, store=store, workspace=c.workspace
        )
    with enter(c.resource) as live:
        authority = Authority()
        records = map_state_qualifications(
            store, c.resource.controls, authority, c.resource.spec, live.site
        )
        env: EnvironmentSelection | None = None
        env_ref: EvidenceRef | None = None
        plan: ResetPlan | None = None
        plan_ref: EvidenceRef | None = None

        def environment(
            snapshot: OverlaySnapshot | NavigationSnapshot,
        ) -> EnvironmentBaseline:
            nonlocal env, env_ref, plan, plan_ref
            assert c.snapshot_ref is not None
            env = EnvironmentSelection(
                scope=c.scope,
                spec_ref=spec_ref,
                site_spec_ref=put(store, c.resource.spec),
                site_started_ref=put(store, live.site),
                snapshot_ref=c.snapshot_ref,
            )
            env_ref = put(store, env)
            browser_token = (
                b.resource.spec.token
                if b is not None
                else AllocationToken(
                    allocation_id="synthetic-browser",
                    owner=c.scope.owner,
                    scope="attempt",
                    attempt_id=c.scope.attempt_id,
                    resource_kind="browser",
                    expected_resource_id="synthetic-browser",
                    provider_id="fixed-browser-worker",
                    provider_version="3",
                    recovery_ref=c.task_recovery,
                )
            )
            plan = ResetPlan(
                scope=c.scope,
                parent_operation_id="prepare",
                spec_ref=spec_ref,
                task_recovery_ref=c.task_recovery,
                environment_recovery_ref=token.recovery_ref,
                attempt_allocations=(browser_token,),
            )
            plan_ref = put(
                store, plan
            )  # Before physical prepare, including failure cases.
            op = c.request("inspect", "environment").operation.model_copy(
                update={"recovery_ref": token.recovery_ref}
            )
            c.observer = "controller"
            try:
                ref = records.publish_environment(env_ref, op)
                return records.load_environment(env_ref, ref, op)
            finally:
                c.observer = "worker"

        preparation: PreparedMapCase | NavigationPreparedCase
        if isinstance(c.private, NavigationSpec):
            preparation = prepare_navigation(c, live, environment=environment)
        else:
            preparation = prepare(c, live, environment=environment)
        assert (
            env is not None
            and env_ref is not None
            and plan is not None
            and plan_ref is not None
        )
        try:
            yield QualifiedMapCase(
                c,
                live,
                preparation,
                env,
                env_ref,
                records,
                authority,
                plan,
                plan_ref,
                b,
            )
        finally:
            c.observer = "worker"


def restore(
    c: QualifiedMapCase,
    *,
    closure_refs: tuple[EvidenceRef, ...] | None = None,
    forced: bool = False,
) -> ResetSelection:
    original = c.original
    store = original.resource.evidence
    if closure_refs is None:
        assert (
            c.browser is None
        )  # Real browser composition must supply original closure.
        closure_refs = (
            put(
                store,
                ClosureReceipt(
                    token=c.plan.attempt_allocations[0],
                    operation_id="fixture-close",
                    status="closed",
                    evidence=(c.environment_ref,),
                ),
            ),
        )
    if forced:
        original.generation.force()
    original.observer = "worker"
    request = original.request("restore")
    result = c.live.tasks.execute_task(request, control=guard())
    resume = original.resume_request(result)
    recorder = RecordedSiteResume(c.live.resume, store, ResumeAuthority(store))
    resumed_ref = recorder.resume(resume, control=guard())
    assert recorder.intent_ref is not None
    original.observer = "controller"
    return ResetSelection(
        environment_selection_ref=c.environment_ref,
        plan_ref=c.plan_ref,
        restore_request_ref=put(store, request),
        restore_result_ref=resume.restore_result_ref,
        resume_request_ref=put(store, resume),
        resume_result_ref=resumed_ref,
        resume_intent_ref=recorder.intent_ref,
        closure_refs=closure_refs,
    )

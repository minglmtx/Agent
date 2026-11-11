"""One actual fresh source qualification. Engineering authority, no Actor right.

Predeclare supported coverage and browser/reset intent before prepare; preserve
actual phase facts. Existing unknown historical sources are never rewritten.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Literal
from collections.abc import Callable
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
from lab_generate_skill.adapters.plans.prepared_browser import read_operation
import json
import pytest
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.lifecycle import (
    RecoveryPlan,
    AllocationToken,
    ClosureReceipt,
    OperationContext,
)
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.state_checks import InitialStateSpec, StateChecks
from lab_generate_skill.domain.state_qualification import (
    EnvironmentSelection,
    ResetSelection,
)
from lab_generate_skill.domain.reset import (
    ResetPlan,
    ResetInputs,
    ResetReceipt,
    assemble_reset,
)
from lab_generate_skill.domain.baseline import (
    BaselineInputs,
    BaselineReceipt,
    InitialStateChecks,
    assemble_baseline,
)
from lab_generate_skill.domain.preparation import (
    PreparationReceipt,
    EnvironmentBaseline,
)
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.initial_observation import (
    InitialObservationSelection,
    InitialObservationInputs,
)
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeRequest
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.public_context import (
    PublicContextInputs,
    PublicContextReceipt,
    assemble_public_context,
)
from lab_generate_skill.domain.initial_equivalence import (
    EquivalenceInputs,
    EquivalenceReceipt,
)
from lab_generate_skill.bootstrap.admin_state_qualification import (
    admin_state_qualifications,
)
from lab_generate_skill.bootstrap.admin_initial_observation import (
    admin_initial_observations,
)
from lab_generate_skill.bootstrap.shopping_state_qualification import (
    shopping_state_qualifications,
)
from lab_generate_skill.bootstrap.shopping_initial_observation import (
    shopping_initial_observations,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_policy import (
    order_eta_initial_spec,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_recovery import (
    OrderEtaRecoverySnapshot,
)
from lab_generate_skill.adapters.storage.initial_observations import (
    EvidenceInitialObservations,
)
from lab_generate_skill.ports.initial_observation import InitialObservationAuthority
from lab_generate_skill.sites.map.tasks.overlay_recovery import OverlaySnapshot
from lab_generate_skill.sites.map.tasks.navigation_recovery import NavigationSnapshot
from lab_generate_skill.adapters.storage.state_records import EvidenceStateRecords
from lab_generate_skill.adapters.storage.context_records import EvidenceContextRecords
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.adapters.sites.resource import RegisteredSite
from lab_generate_skill.sites.shopping_admin.tasks.product_state_policy import (
    product_initial_state_spec,
    ENVIRONMENT_RESET_CHECKS,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_recovery_contract import (
    ProductRecoverySnapshot,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from site_resource_fixtures import Case
from browser_resource_fixtures import ResourceCase
from site_preparation_native import NativePreparation
from shopping_preparation_native import ShoppingPreparation
from gitlab_preparation_native import GitlabPreparation
from gitlab_source_selection import GitlabSourceSelection
from lab_generate_skill.bootstrap.gitlab_group_records import (
    group_state_qualifications,
    group_initial_observations,
)
from lab_generate_skill.sites.gitlab.tasks.group_recovery import GroupRecoverySnapshot
from lab_generate_skill.bootstrap.gitlab_ssh_records import (
    gitlab_state_qualifications,
    gitlab_initial_observations,
)
from lab_generate_skill.sites.gitlab.tasks.ssh_key_policy import ssh_key_initial_spec
from lab_generate_skill.sites.gitlab.tasks.ssh_key_recovery import (
    SshKeyRecoverySnapshot,
)
from reddit_preparation_native import RedditPreparation
from reddit_source_selection import RedditSourceSelection
from lab_generate_skill.bootstrap.reddit_image_records import (
    reddit_state_qualifications,
    reddit_initial_observations,
)
from lab_generate_skill.sites.reddit.tasks.image_policy import image_initial_spec
from lab_generate_skill.sites.reddit.tasks.image_recovery import ImageRecoverySnapshot
from prepared_browser_native import observe_prepared
from site_resume_native import resume_original
from test_admin_description_inputs import public_task
from test_slurm_commands import guard


def selected_gitlab_source(
    c: Case, selection: GitlabSourceSelection | None
) -> GitlabSourceSelection | None:
    if selection is not None and not isinstance(selection, GitlabSourceSelection):
        raise TypeError("Explicit validated GitLab selection required")
    if c.spec.configuration.site_id == "gitlab":
        if selection is None:
            raise ValueError("GitLab source requires an explicit original selection")
        selection.check_configuration(c.spec.configuration)
    elif selection is not None:
        raise ValueError("Selected GitLab input requires its original site")
    return selection


def configure_qualification(
    c: Case,
    *,
    reddit_selection: RedditSourceSelection | None = None,
    gitlab_selection: GitlabSourceSelection | None = None,
) -> InitialStateSpec:
    if reddit_selection is not None:
        if not isinstance(reddit_selection, RedditSourceSelection):
            raise TypeError("Explicit validated Reddit selection required")
        if c.spec.configuration.site_id != "reddit":
            raise ValueError(
                "Selected Reddit declaration cannot configure another site"
            )
    gitlab_selection = selected_gitlab_source(c, gitlab_selection)
    from test_shopping_order_eta_inputs import public_task as shopping_task

    reddit = c.spec.configuration.site_id == "reddit"
    from test_reddit_image_inputs import public_task as reddit_task

    shopping = c.spec.configuration.site_id == "shopping"
    gitlab = c.spec.configuration.site_id == "gitlab"
    from test_gitlab_ssh_key_inputs import public_task as gitlab_task

    if reddit:
        spec = image_initial_spec(
            reddit_task().identity
            if reddit_selection is None
            else reddit_selection.public_template.identity
        )
    elif gitlab:
        assert gitlab_selection is not None
        spec = gitlab_selection.initial_spec
    elif shopping:
        spec = order_eta_initial_spec(shopping_task().identity)
    else:
        spec = product_initial_state_spec(public_task().identity)

    def put(value: Any) -> EvidenceRef:
        return c.evidence.put(
            value.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema=value.schema_version,
                visibility="private",
                producer="native-preparation-engineering",
            ),
            control=guard(10),
        )

    recovery = RecoveryPlan(
        recovery_id=(
            "reddit-environment"
            if reddit
            else (
                "gitlab-environment"
                if gitlab
                else "shopping-environment" if shopping else "admin-environment"
            )
        ),
        owner=c.spec.token.owner,
        baseline_ref=put(spec),
        restore_component_id=(
            "reddit-services"
            if reddit
            else (
                "gitlab-services"
                if gitlab
                else "shopping-services" if shopping else "admin-frontend"
            )
        ),
        restore_component_version="1",
        state_coverage=spec.environment_reset_checks,
    )
    ref = put(recovery)
    config = c.spec.configuration.model_copy(
        update={"token": c.spec.token.model_copy(update={"recovery_ref": ref})}
    )
    c.spec = c.spec.model_copy(update={"configuration": config})
    c.op = c.op.model_copy(update={"recovery_ref": ref})
    return spec


class QualifiedSource:
    site: SiteHandle

    def __init__(
        self,
        c: Case,
        site: RegisteredSite,
        spec: InitialStateSpec,
        *,
        allowed_actions: tuple[str, ...] | None = None,
        reddit_selection: RedditSourceSelection | None = None,
        gitlab_selection: GitlabSourceSelection | None = None,
    ) -> None:
        if reddit_selection is not None:
            if not isinstance(reddit_selection, RedditSourceSelection):
                raise TypeError("Explicit validated Reddit selection required")
            if c.spec.configuration.site_id != "reddit":
                raise ValueError(
                    "Selected Reddit declaration cannot initialize another site"
                )
        gitlab_selection = selected_gitlab_source(c, gitlab_selection)
        self.gitlab_selection = gitlab_selection
        self.c, self.site = c, site
        preparation_type = (
            RedditPreparation
            if c.spec.configuration.site_id == "reddit"
            else (
                ShoppingPreparation
                if c.spec.configuration.site_id == "shopping"
                else NativePreparation
            )
        )
        self.native: NativePreparation
        if gitlab_selection is not None:
            self.native = GitlabPreparation(
                c,
                site.site.instance.endpoint,
                state_spec=spec,
                allowed_actions=allowed_actions,
                selection=gitlab_selection,
            )
        else:
            self.native = (
                preparation_type(
                    c,
                    site.site.instance.endpoint,
                    state_spec=spec,
                    allowed_actions=allowed_actions,
                )
                if reddit_selection is None
                else RedditPreparation(
                    c,
                    site.site.instance.endpoint,
                    state_spec=spec,
                    allowed_actions=allowed_actions,
                    native_input=reddit_selection.native,
                    public_input=reddit_selection.public_at(
                        site.site.instance.endpoint, allowed_actions
                    ),
                )
            )
        factory = (
            reddit_state_qualifications
            if c.spec.configuration.site_id == "reddit"
            else (
                (
                    group_state_qualifications
                    if gitlab_selection is not None and gitlab_selection.group
                    else gitlab_state_qualifications
                )
                if c.spec.configuration.site_id == "gitlab"
                else (
                    shopping_state_qualifications
                    if c.spec.configuration.site_id == "shopping"
                    else admin_state_qualifications
                )
            )
        )
        self.records = factory(c.evidence, c.controls, self)
        self.states = EvidenceStateRecords(c.evidence, c.controls, self)
        self.contexts = EvidenceContextRecords(c.evidence, c.controls, self)
        self.saved: dict[str, Any] = {}

    def parse_snapshot(
        self, result: SiteTaskResult
    ) -> (
        ProductRecoverySnapshot
        | OrderEtaRecoverySnapshot
        | SshKeyRecoverySnapshot
        | GroupRecoverySnapshot
        | ImageRecoverySnapshot
        | OverlaySnapshot
        | NavigationSnapshot
    ):
        snapshot_type = (
            ImageRecoverySnapshot
            if self.c.spec.configuration.site_id == "reddit"
            else (
                (
                    GroupRecoverySnapshot
                    if self.gitlab_selection is not None and self.gitlab_selection.group
                    else SshKeyRecoverySnapshot
                )
                if self.c.spec.configuration.site_id == "gitlab"
                else (
                    OrderEtaRecoverySnapshot
                    if self.c.spec.configuration.site_id == "shopping"
                    else ProductRecoverySnapshot
                )
            )
        )
        return snapshot_type.model_validate_json(result.private_result)

    def after_snapshot(
        self,
        request: SiteTaskRequest,
        result: SiteTaskResult,
        snapshot_ref: EvidenceRef,
    ) -> None:
        n = self.native
        snapshot = self.parse_snapshot(result)
        assert (
            snapshot.request == request
            and n.c.evidence.read(snapshot_ref, control=guard(10))
            == result.private_result.encode()
        )
        scope = StateScope(
            owner=self.c.spec.token.owner,
            task=request.task,
            attempt_id=n.attempt_id,
            context_id=n.context_id,
        )
        selection = EnvironmentSelection(
            scope=scope,
            spec_ref=n.spec_ref,
            site_spec_ref=n.put(self.c.spec),
            site_started_ref=n.put(self.site.site),
            snapshot_ref=snapshot_ref,
        )
        selection_ref = n.put(selection)
        self.saved.update(
            environment_selection=selection,
            environment_selection_ref=selection_ref,
            snapshot=snapshot,
            snapshot_ref=snapshot_ref,
        )
        op = request.operation.model_copy(
            update={
                "operation_id": "qualified-environment",
                "recovery_ref": self.c.spec.token.recovery_ref,
                "deadline": datetime.now(timezone.utc) + timedelta(seconds=30),
            }
        )
        env_ref = self.records.publish_environment(selection_ref, op)
        self.environment = self.records.load_environment(selection_ref, env_ref, op)
        self.saved["environment_ref"] = env_ref
        browser_recovery = RecoveryPlan(
            recovery_id="source-browser-close",
            owner=scope.owner,
            attempt_id=scope.attempt_id,
            baseline_ref=n.spec_ref,
            restore_component_id="browser-close",
            restore_component_version="1",
            state_coverage=("browser-processes",),
        )
        self.browser_token = AllocationToken(
            allocation_id="browser-allocation",
            owner=scope.owner,
            scope="attempt",
            attempt_id=scope.attempt_id,
            resource_kind="browser",
            expected_resource_id="browser-instance",
            provider_id="fixed-browser-worker",
            provider_version="3",
            recovery_ref=n.put(browser_recovery),
        )
        self.plan = ResetPlan(
            scope=scope,
            parent_operation_id="native-task-prepare",
            spec_ref=n.spec_ref,
            task_recovery_ref=n.recovery_ref,
            environment_recovery_ref=self.c.spec.token.recovery_ref,
            attempt_allocations=(self.browser_token,),
        )
        self.plan_ref = n.put(self.plan)

    def verify(
        self,
        scope: StateScope,
        selection_ref: EvidenceRef,
        phase: Literal["environment", "reset"],
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        assert scope == self.saved["environment_selection"].scope and (
            op.run_id,
            op.owner_id,
        ) == (scope.owner.run_id, scope.owner.owner_id)
        read = self.c.op.model_copy(
            update={
                "operation_id": "qualified-read-" + op.operation_id,
                "deadline": op.deadline,
                "mode": "cleanup",
                "parent_operation_id": self.c.op.operation_id,
                "cancellation_ref": None,
            }
        )
        assert self.c.journal.read(self.c.spec.token, read).state == "acquired"
        if phase == "environment":
            assert selection_ref == self.saved["environment_selection_ref"]
            assert (
                self.c.evidence.read(self.saved["snapshot_ref"], control=control)
                == self.saved["snapshot"].model_dump_json().encode()
            )
        else:
            assert selection_ref == self.saved["reset_selection_ref"]
            assert (
                self.saved["browser_closed_before_restore"]
                and self.saved["resumed_after_restore"]
            )

    def observe(
        self,
        publication: PreparedPublication,
        root: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        on_session: (
            Callable[[ResourceCase, EvidenceBrowserSession, dict[str, Any]], None]
            | None
        ) = None,
    ) -> dict[str, Any]:
        self.publication = publication

        def opened(
            b: ResourceCase, session: EvidenceBrowserSession, observed: dict[str, Any]
        ) -> None:
            self.initialize_session(b, session, observed)
            if on_session is not None:
                on_session(b, session, observed)

        observed = observe_prepared(
            self.native,
            self.site.site,
            publication,
            root,
            monkeypatch,
            declared_token=self.browser_token,
            on_session=opened,
        )
        closure = ClosureReceipt.model_validate_json(
            json.dumps(observed["browser_ending"]["details"]["closure"])
        )
        assert closure.token == self.browser_token and closure.status == "closed"
        self.saved.update(
            browser_closure_ref=self.native.put(closure),
            browser_closed_before_restore=True,
        )
        return observed

    def initialize_session(
        self, b: ResourceCase, session: EvidenceBrowserSession, observed: dict[str, Any]
    ) -> None:
        self.initial(b, observed)

    def initial_records(
        self, authority: InitialObservationAuthority
    ) -> EvidenceInitialObservations:
        initial_factory = (
            reddit_initial_observations
            if self.c.spec.configuration.site_id == "reddit"
            else (
                (
                    group_initial_observations
                    if self.gitlab_selection is not None and self.gitlab_selection.group
                    else gitlab_initial_observations
                )
                if self.c.spec.configuration.site_id == "gitlab"
                else (
                    shopping_initial_observations
                    if self.c.spec.configuration.site_id == "shopping"
                    else admin_initial_observations
                )
            )
        )
        return initial_factory(
            self.c.evidence, self.c.controls, self.native.records, authority
        )

    def initial(self, b: ResourceCase, observed: dict[str, Any]) -> None:
        n = self.native
        record = b.journal.read(b.spec.token, b.op)
        intent = ResourceAcquisitionIntent.model_validate_json(
            b.evidence.read(record.events[1].evidence[0], control=guard(10))
        )
        self.saved["browser_spec_ref"] = intent.configuration_ref
        selection = InitialObservationSelection(
            preparation=self.publication,
            browser_spec_ref=intent.configuration_ref,
            browser_acquired_ref=EvidenceRef.model_validate(
                observed["browser_started_ref"]
            ),
        )

        class InitialAuthority:
            def verify(
                self,
                inputs: InitialObservationInputs,
                checks: StateChecks,
                operation: OperationContext,
                control: OperationControl,
            ) -> None:
                assert inputs.selection == selection and checks.status == "pass"
                assert b.journal.read(b.spec.token, b.op).state == "acquired"
                control.checkpoint()

        assert n.request is not None
        initial_op = n.request.operation.model_copy(
            update={
                "operation_id": "qualified-initial",
                "deadline": datetime.now(timezone.utc) + timedelta(seconds=30),
            }
        )
        checks = self.initial_records(InitialAuthority())
        initial_ref = checks.publish(selection, initial_op)
        initial = checks.load(selection, initial_ref, initial_op)
        prepared = n.records.load(
            self.publication,
            n.request.operation.cleanup(
                "qualified-prepared-read", now=datetime.now(timezone.utc), seconds=30
            ),
        )
        preparation = PreparationReceipt.model_validate_json(
            self.c.evidence.read(self.publication.preparation_ref, control=guard(10))
        )
        observation_ref = EvidenceRef.model_validate(
            observed["initial_observation_ref"]
        )
        observation = Observation.model_validate_json(
            self.c.evidence.read(observation_ref, control=guard(10))
        )
        inputs = BaselineInputs(
            binding=n.binding,
            public_task=n.public,
            spec=n.spec,
            spec_ref=n.spec_ref,
            environment=self.environment,
            environment_ref=self.publication.selection.environment_ref,
            preparation=preparation,
            preparation_ref=self.publication.preparation_ref,
            prepared=prepared,
            prepared_ref=self.publication.prepared_ref,
            observation=observation,
            observation_ref=observation_ref,
            initial=initial,
            initial_ref=initial_ref,
        )
        op = initial_op.model_copy(update={"operation_id": "qualified-baseline"})
        receipt = assemble_baseline(inputs, op)
        assert receipt.status == "ready" and observation.sequence == 0
        self.saved.update(
            baseline_inputs=inputs, baseline=receipt, initial_ref=initial_ref
        )
        ref = self.states.publish_baseline(receipt, op)
        assert self.states.load_baseline(ref, op) == receipt
        self.saved["baseline_ref"] = ref
        observed.update(
            environment_status="pass",
            complete_baseline=True,
            baseline_inputs_ref=n.raw(
                inputs.model_dump_json().encode(), "baseline-inputs/1"
            ).model_dump(mode="json"),
            baseline_ref=ref.model_dump(mode="json"),
            initial_checks_ref=initial_ref.model_dump(mode="json"),
            actor_authorized=False,
        )

    def verify_baseline(
        self, inputs: BaselineInputs, receipt: BaselineReceipt, op: OperationContext
    ) -> None:
        control = self.c.controls.bind(op)
        actual = self.records.checks.environment(
            self.saved["environment_selection"],
            self.saved["environment_selection_ref"],
            self.environment.operation,
            control,
        )
        assert (
            inputs == self.saved["baseline_inputs"]
            and receipt == self.saved["baseline"]
        )
        assert (
            inputs.environment == actual
            and inputs.initial_ref == self.saved["initial_ref"]
        )
        # Recompute the original prepared record rather than assuming a
        # site-specific check's position inside its evidence tuple.
        assert self.native.request is not None
        assert (
            self.native.records.load(
                self.publication, read_operation(self.native.request.operation, op)
            )
            == inputs.prepared
        )
        assert (
            self.c.evidence.read(self.publication.preparation_ref, control)
            == inputs.preparation.model_dump_json().encode()
        )

    def verify_reset(
        self, inputs: ResetInputs, receipt: ResetReceipt, op: OperationContext
    ) -> None:
        checked = self.records.checks.reset(
            self.saved["reset_selection"],
            self.saved["reset_selection_ref"],
            self.c.controls.bind(op),
        )
        assert (
            inputs.task.checks,
            inputs.environment.checks,
            inputs.health.checks,
            inputs.plan,
            inputs.closures,
        ) == (
            checked.task,
            checked.environment,
            checked.health,
            checked.plan,
            checked.closures,
        )
        assert (
            receipt == self.saved["reset"]
            and self.saved["browser_closed_before_restore"]
        )

    def verify_context(
        self,
        inputs: PublicContextInputs,
        receipt: PublicContextReceipt,
        op: OperationContext,
    ) -> None:
        assert (
            inputs.baseline_ref == self.saved["baseline_ref"]
            and inputs.reset_ref == self.saved["reset_ref"]
        )
        assert (
            inputs.context.initial_observation_ref
            == self.saved["baseline"].observation_ref
        )
        assert inputs.baseline.status == "ready" and inputs.reset.status == "safe"

    def verify_equivalence(
        self,
        inputs: EquivalenceInputs,
        receipt: EquivalenceReceipt,
        op: OperationContext,
    ) -> None:
        raise PermissionError(
            "No candidate equivalence measured in source qualification"
        )

    def after_restore(
        self, request: SiteTaskRequest, result: SiteTaskResult
    ) -> dict[str, Any]:
        assert self.saved["browser_closed_before_restore"]
        n = self.native
        resumed = resume_original(
            self.c,
            self.site,
            request,
            result,
            browser_closure_ref=self.saved["browser_closure_ref"],
        )
        resume_request = SiteResumeRequest.model_validate_json(
            json.dumps(resumed["request"])
        )
        selection = ResetSelection(
            environment_selection_ref=self.saved["environment_selection_ref"],
            plan_ref=self.plan_ref,
            restore_request_ref=n.put(request),
            restore_result_ref=resume_request.restore_result_ref,
            resume_request_ref=n.put(resume_request),
            resume_result_ref=EvidenceRef.model_validate(resumed["result_ref"]),
            resume_intent_ref=EvidenceRef.model_validate(resumed["intent_ref"]),
            closure_refs=(self.saved["browser_closure_ref"],),
        )
        selection_ref = n.put(selection)
        self.saved.update(
            reset_selection=selection,
            reset_selection_ref=selection_ref,
            resumed_after_restore=True,
        )
        assert n.request is not None
        op = n.request.operation.cleanup(
            "qualified-reset", now=datetime.now(timezone.utc), seconds=30
        ).model_copy(update={"recovery_ref": self.c.spec.token.recovery_ref})
        inputs = self.records.publish_reset_facts(selection_ref, op)
        reset = assemble_reset(inputs, op)
        assert reset.status == "safe"
        self.saved["reset"] = reset
        reset_ref = self.states.publish_reset(reset, op)
        assert self.states.load_reset(reset_ref, op) == reset
        self.saved["reset_ref"] = reset_ref
        context = PublicConstructionContext(
            context_id=self.plan.scope.context_id,
            task=n.public,
            initial_observation_ref=self.saved["baseline"].observation_ref,
        )
        public = n.put(context, "public")
        context_inputs = PublicContextInputs(
            context=context,
            context_ref=public,
            baseline_inputs=self.saved["baseline_inputs"],
            baseline=self.saved["baseline"],
            baseline_ref=self.saved["baseline_ref"],
            reset_inputs=inputs,
            reset=reset,
            reset_ref=reset_ref,
        )
        freeze = self.c.op.model_copy(
            update={
                "operation_id": "qualified-context",
                "attempt_id": None,
                "allocation_id": None,
                "recovery_ref": None,
                "deadline": datetime.now(timezone.utc) + timedelta(seconds=30),
            }
        )
        receipt = assemble_public_context(context_inputs, freeze)
        context_ref = self.contexts.publish_context(receipt, freeze)
        assert self.contexts.load_context(context_ref, freeze) == receipt
        return dict(
            engineering_only=True,
            formal_source_admission=False,
            reset_inputs_ref=n.raw(
                inputs.model_dump_json().encode(), "reset-inputs/1"
            ).model_dump(mode="json"),
            baseline_status="ready",
            reset_status="safe",
            baseline_ref=self.saved["baseline_ref"].model_dump(mode="json"),
            reset_ref=reset_ref.model_dump(mode="json"),
            public_context_ref=public.model_dump(mode="json"),
            context_receipt_ref=context_ref.model_dump(mode="json"),
            reset_selection_ref=selection_ref.model_dump(mode="json"),
            environment_selection_ref=self.saved[
                "environment_selection_ref"
            ].model_dump(mode="json"),
            reset_plan_ref=self.plan_ref.model_dump(mode="json"),
            original_observation_ref=context.initial_observation_ref.model_dump(
                mode="json"
            ),
            frontend_resumption=resumed,
            actor_authorized=False,
        )

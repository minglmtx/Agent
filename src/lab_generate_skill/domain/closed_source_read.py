"""Exact retained Map graph and optional binding facts for readonly verification."""

from typing import Literal, Self, Annotated, TypeAlias
from pydantic import (
    Field,
    model_validator,
    model_serializer,
    SerializerFunctionWrapHandler,
)
from typing import Any
from .validation import Contract
from .evidence import EvidenceRef
from .evidence_read_scope import EvidenceReadScope
from .initial_observation import InitialObservationSelection
from .map_initial_capture import MapInitialEvidence
from .site_resource import SiteResourceSpec
from .browser_resource import BrowserResourceSpec
from .lifecycle import ResourceRecord, ResourceOwner
from .state_scope import private_state_ref
from .task import PublicTask, TaskBinding
from .run_plan import RunPlan
from .task_execution import TaskExecutionPlan
from .baseline import BaselineReceipt
from .reset import ResetReceipt
from .construction_inputs import PublicConstructionContext
from .public_context import PublicContextReceipt
from .admin_navigation_browser_initialization import AdminNavigationInitialization
from .gitlab_browser_initialization import GitlabGroupInitialization
from .closed_shopping_source import ClosedCategoryNavigationReadMaterial
from .native_private_json import GITLAB_GROUP_PRIVATE_JSON
from pathlib import PurePosixPath


class ClosedMapReadMaterial(Contract):
    schema_version: Literal["closed-map-read-material/1"] = "closed-map-read-material/1"
    context_ref: EvidenceRef
    environment_ref: EvidenceRef
    reset_ref: EvidenceRef
    initial: InitialObservationSelection
    initial_capture: MapInitialEvidence
    site: SiteResourceSpec
    browser: BrowserResourceSpec
    site_record: ResourceRecord
    browser_record: ResourceRecord

    @model_validator(mode="after")
    def closed(self) -> Self:
        for ref, schema in (
            (self.context_ref, "public-context-receipt/1"),
            (self.environment_ref, "environment-selection/1"),
            (self.reset_ref, "reset-selection/1"),
        ):
            private_state_ref(ref, schema)
        if (
            self.site.configuration.site_id != "map"
            or self.site_record.token != self.site.token
            or self.browser_record.token != self.browser.token
            or self.site_record.state != "closed"
            or self.browser_record.state != "closed"
            or self.site.token.owner != self.browser.token.owner
        ):
            raise ValueError("Original closed Map site/browser declarations required")
        return self


class ClosedSourceBindingInput(Contract):
    schema_version: Literal["closed-source-binding-input/1"] = (
        "closed-source-binding-input/1"
    )
    binding: TaskBinding
    public_task: PublicTask
    private_spec_json: str = Field(min_length=1, max_length=2 * 1024**2)
    baseline_json: str = Field(min_length=1, max_length=2 * 1024**2)


class ClosedAdminNavigationReadMaterial(Contract):
    schema_version: Literal["closed-admin-navigation-read-material/1"] = (
        "closed-admin-navigation-read-material/1"
    )
    context_ref: EvidenceRef
    environment_ref: EvidenceRef
    reset_ref: EvidenceRef
    initial: InitialObservationSelection
    capture_intent_ref: EvidenceRef
    capture_result_ref: EvidenceRef
    site: SiteResourceSpec
    browser: BrowserResourceSpec
    site_record: ResourceRecord
    browser_record: ResourceRecord

    @model_validator(mode="after")
    def closed(self) -> Self:
        for ref, schema in (
            (self.context_ref, "public-context-receipt/1"),
            (self.environment_ref, "environment-selection/1"),
            (self.reset_ref, "reset-selection/1"),
            (self.capture_intent_ref, "browser-capture-intent/1"),
            (self.capture_result_ref, "browser-capture-result/1"),
        ):
            private_state_ref(ref, schema)
        inputs, selected = (
            self.site.configuration.admin_navigation_inputs,
            self.browser.configuration.initialization,
        )
        if (
            self.site.configuration.site_id != "shopping_admin"
            or inputs is None
            or not isinstance(selected, AdminNavigationInitialization)
            or self.site_record.token != self.site.token
            or self.browser_record.token != self.browser.token
            or self.site_record.state != "closed"
            or self.browser_record.state != "closed"
            or self.site.token.owner != self.browser.token.owner
            or inputs.scope != self.browser.configuration.spec.scope
            or selected.native_contract_sha256 != inputs.native_contract_sha256
        ):
            raise ValueError(
                "Original closed Admin navigation source declarations required"
            )
        selected.check(self.browser.configuration.spec)
        return self


class ClosedGroupReadMaterial(Contract):
    schema_version: Literal["closed-gitlab-group-read-material/1"] = (
        "closed-gitlab-group-read-material/1"
    )
    context_ref: EvidenceRef
    environment_ref: EvidenceRef
    reset_ref: EvidenceRef
    initial: InitialObservationSelection
    capture_intent_ref: EvidenceRef
    capture_result_ref: EvidenceRef
    site: SiteResourceSpec
    browser: BrowserResourceSpec
    site_record: ResourceRecord
    browser_record: ResourceRecord

    @model_validator(mode="after")
    def closed(self) -> Self:
        for ref, schema in (
            (self.context_ref, "public-context-receipt/1"),
            (self.environment_ref, "environment-selection/1"),
            (self.reset_ref, "reset-selection/1"),
            (self.capture_intent_ref, "browser-capture-intent/1"),
            (self.capture_result_ref, "browser-capture-result/1"),
        ):
            private_state_ref(ref, schema)
        cfg, selected = (
            self.site.configuration,
            self.browser.configuration.initialization,
        )
        scope = self.browser.configuration.spec.scope
        if (
            cfg.site_id != "gitlab"
            or cfg.private_evidence is None
            or cfg.private_evidence.profile != GITLAB_GROUP_PRIVATE_JSON
            or not isinstance(selected, GitlabGroupInitialization)
            or (
                scope.task.site,
                scope.task.family,
                scope.task.contract_version,
                scope.task.split,
            )
            != ("gitlab", "group_creation", 1, "train")
            or self.site_record.token != self.site.token
            or self.browser_record.token != self.browser.token
            or self.site_record.state != "closed"
            or self.browser_record.state != "closed"
            or self.site.token.owner != scope.owner
            or self.site.token.owner != self.browser.token.owner
        ):
            raise ValueError(
                "Original closed Group source site/browser declarations required"
            )
        selected.check(self.browser.configuration.spec)
        return self


ClosedSourceMaterial: TypeAlias = Annotated[
    ClosedMapReadMaterial
    | ClosedAdminNavigationReadMaterial
    | ClosedGroupReadMaterial
    | ClosedCategoryNavigationReadMaterial,
    Field(discriminator="schema_version"),
]


class ClosedSourcePublicationInput(Contract):
    """Proposed immutable summaries, never a publication or source grant.

    The fixed reader validates these through the original record publishers
    without disk writes. Only the original parent can persist and seal them.
    """

    schema_version: Literal["closed-source-publication-input/1"] = (
        "closed-source-publication-input/1"
    )
    public: PublicConstructionContext
    baseline: BaselineReceipt
    reset: ResetReceipt
    context: PublicContextReceipt

    @model_validator(mode="after")
    def same_scope(self) -> Self:
        if (
            self.baseline.scope != self.context.scope
            or self.reset.scope != self.context.scope
            or self.public.task.identity != self.context.scope.task
            or self.baseline.status != "ready"
            or self.reset.status != "safe"
        ):
            raise ValueError(
                "Proposed source summaries changed original ready/safe scope"
            )
        return self


from .actor_acquisition_inputs import ActorAcquisitionInputs
from .preparation_read import PreparationReadRequest
from .baseline_read import BaselineReadRequest


class ClosedSourceReadCommand(Contract):
    schema_version: Literal[
        "closed-source-read-command/1",
        "closed-source-read-command/2",
        "closed-source-read-command/3",
    ] = "closed-source-read-command/1"
    scope: EvidenceReadScope
    workspace_root: str = Field(min_length=1, max_length=4096)
    material: ClosedSourceMaterial
    kind: Literal[
        "context",
        "context_inputs",
        "binding",
        "publication",
        "plan_inputs",
        "binding_reference",
        "execution_source",
        "execution_source_claim",
        "actor_acquisition",
        "preparation_inputs",
        "baseline_inputs",
    ]
    binding: ClosedSourceBindingInput | None = None
    publication: ClosedSourcePublicationInput | None = None
    plan_inputs: RunPlan | None = None
    binding_reference: EvidenceRef | None = None
    execution_plan: TaskExecutionPlan | None = None
    actor_inputs: ActorAcquisitionInputs | None = None
    preparation_read: PreparationReadRequest | None = None
    baseline_read: BaselineReadRequest | None = None
    current_initial_owner: ResourceOwner | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if self.kind != "binding":
            value.pop("binding", None)
        if self.kind != "publication":
            value.pop("publication", None)
        if self.kind != "plan_inputs":
            value.pop("plan_inputs", None)
        if self.kind != "binding_reference":
            value.pop("binding_reference", None)
        if self.kind not in ("execution_source", "execution_source_claim"):
            value.pop("execution_plan", None)
        if self.kind != "actor_acquisition":
            value.pop("actor_inputs", None)
        if self.kind != "preparation_inputs":
            value.pop("preparation_read", None)
        if self.kind != "baseline_inputs":
            value.pop("baseline_read", None)
        if self.current_initial_owner is None:
            value.pop("current_initial_owner", None)
        return value

    @model_validator(mode="after")
    def selected(self) -> Self:
        if self.schema_version == "closed-source-read-command/3":
            owner = self.current_initial_owner
            request = self.preparation_read or self.baseline_read
            if (
                owner is None
                or owner != self.scope.binding.owner
                or self.kind not in ("preparation_inputs", "baseline_inputs")
                or request is None
                or (request.operation.run_id, request.operation.owner_id)
                != (owner.run_id, owner.owner_id)
            ):
                raise ValueError(
                    "Current initial proof requires the exact current read owner"
                )
        elif "current_initial_owner" in self.model_fields_set:
            raise ValueError("Historical commands forbid current initial owner fields")
        if (self.schema_version == "closed-source-read-command/2") != (
            self.kind == "execution_source_claim"
        ):
            raise ValueError("Command2 requires the explicit execution claim proof")
        if (self.kind == "baseline_inputs") != (self.baseline_read is not None):
            raise ValueError(
                "Only baseline input reads carry an exact baseline request"
            )
        if self.kind != "baseline_inputs" and "baseline_read" in self.model_fields_set:
            raise ValueError("Other source reads forbid baseline-only fields")
        if self.kind == "baseline_inputs" and any(
            name in self.model_fields_set
            for name in (
                "binding",
                "publication",
                "plan_inputs",
                "binding_reference",
                "execution_plan",
                "actor_inputs",
                "preparation_read",
            )
        ):
            raise ValueError("Baseline reads forbid other request fields")
        if (self.kind == "preparation_inputs") != (self.preparation_read is not None):
            raise ValueError("Only preparation input reads carry their exact selection")
        if (
            self.kind != "preparation_inputs"
            and "preparation_read" in self.model_fields_set
        ):
            raise ValueError("Other reads forbid preparation-only fields")
        if self.kind == "preparation_inputs" and any(
            name in self.model_fields_set
            for name in (
                "binding",
                "publication",
                "plan_inputs",
                "binding_reference",
                "execution_plan",
                "actor_inputs",
            )
        ):
            raise ValueError("Preparation reads forbid other request fields")
        workspace = PurePosixPath(self.workspace_root)
        if (
            not workspace.is_absolute()
            or str(workspace) != self.workspace_root
            or ".." in workspace.parts
            or "\0" in self.workspace_root
            or "\\" in self.workspace_root
            or self.material.site.configuration.files.workspace_root
            != self.workspace_root
            or not PurePosixPath(self.scope.config.evidence_root).is_relative_to(
                workspace
            )
        ):
            raise ValueError("Source proof must stay in its original workspace")
        if (self.kind == "actor_acquisition") != (self.actor_inputs is not None):
            raise ValueError("Only Actor proof carries original acquisition inputs")
        if self.kind != "actor_acquisition" and "actor_inputs" in self.model_fields_set:
            raise ValueError("Other source reads forbid Actor acquisition fields")
        if self.actor_inputs is not None:
            if (
                any(
                    name in self.model_fields_set
                    for name in (
                        "binding",
                        "publication",
                        "plan_inputs",
                        "binding_reference",
                        "execution_plan",
                    )
                )
                or not self.actor_inputs.supported()
            ):
                raise ValueError(
                    "Actor acquisition proof requires only bounded original inputs"
                )
            binding = self.actor_inputs.binding
            if (
                binding.resource.owner != self.material.site.token.owner
                or binding.release_ref
                != self.material.site.configuration.installation.manifest_ref
            ):
                raise ValueError(
                    "Actor acquisition proof changed original source owner/release"
                )
        if (self.kind in ("execution_source", "execution_source_claim")) != (
            self.execution_plan is not None
        ):
            raise ValueError("Only execution source proof carries its exact task plan")
        if (
            self.kind not in ("execution_source", "execution_source_claim")
            and "execution_plan" in self.model_fields_set
        ):
            raise ValueError("Other source reads forbid execution-only fields")
        if self.kind in ("execution_source", "execution_source_claim"):
            if any(
                name in self.model_fields_set
                for name in (
                    "binding",
                    "publication",
                    "plan_inputs",
                    "binding_reference",
                )
            ):
                raise ValueError("Execution source proof forbids other request fields")
            assert self.execution_plan is not None
            if (
                self.execution_plan.intent.source_kind != "execution"
                or self.execution_plan.source_ref is None
            ):
                raise ValueError("Original single execution source plan required")
        if (self.kind == "binding_reference") != (self.binding_reference is not None):
            raise ValueError(
                "Only task-reference reads carry the exact binding reference"
            )
        if (
            self.kind != "binding_reference"
            and "binding_reference" in self.model_fields_set
        ):
            raise ValueError("Other source reads forbid task-reference fields")
        if self.kind == "binding_reference":
            assert self.binding_reference is not None
            private_state_ref(self.binding_reference, "task-binding/1")
            if any(
                name in self.model_fields_set
                for name in ("binding", "publication", "plan_inputs")
            ):
                raise ValueError("Task-reference reads forbid other request fields")
        if (self.kind == "plan_inputs") != (self.plan_inputs is not None):
            raise ValueError("Only plan input verification carries its exact RunPlan")
        if self.kind != "plan_inputs" and "plan_inputs" in self.model_fields_set:
            raise ValueError("Other source reads forbid plan-only fields")
        if self.kind == "plan_inputs" and (
            "binding" in self.model_fields_set or "publication" in self.model_fields_set
        ):
            raise ValueError("Plan input verification forbids other request fields")
        if (self.kind == "binding") != (self.binding is not None):
            raise ValueError("Only binding reads carry exact task binding inputs")
        if (
            self.kind in ("context", "context_inputs")
            and "binding" in self.model_fields_set
        ):
            raise ValueError("Context reads forbid binding-only fields")
        if (self.kind == "publication") != (self.publication is not None):
            raise ValueError("Only publication validation carries proposed summaries")
        if self.kind != "publication" and "publication" in self.model_fields_set:
            raise ValueError("Readonly context/binding forbids proposed summaries")
        if self.kind == "publication" and "binding" in self.model_fields_set:
            raise ValueError("Publication validation forbids binding-only fields")
        return self

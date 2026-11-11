"""Frozen task-batch RunPlan: method, data, models, resources and capacity.

This is the task execution/construction plan; export, rejudge and trainer
payloads have their own contracts. References freeze inputs, not semantic
approval. Release/split/claim/authorization verification and scheduler admission
remain required consumers before execution. No filesystem paths or credentials
are accepted as substitutes for content-bound inputs.
"""

import json
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .budget import BudgetAuthorization, Money
from .budget_journal import BudgetJournalCapacity, BudgetJournalSnapshot
from .budget_policy import BudgetDispatchPolicy
from .construction_method import ConstructionMethod
from .evidence import EvidenceRef
from .execution import RunBinding
from .identity import Split
from .journal_capacity import JournalCapacity
from .optional_policies import EnabledPolicy, RunPolicies
from .request_ledger import BudgetSnapshot
from .task import TaskBinding
from .validation import Contract, Identifier, NonEmptyText

Role = Literal["actor", "generator", "teacher"]


class RoleModelPlan(Contract):
    schema_version: Literal["role-model-plan/1"] = "role-model-plan/1"
    role: Role
    provider: Identifier
    model: NonEmptyText
    model_binding_ref: EvidenceRef
    parameters_ref: EvidenceRef
    paid: bool


class ConstructionWorkload(Contract):
    schema_version: Literal["construction-workload/1"] = "construction-workload/1"
    kind: Literal["construct_targets"] = "construct_targets"
    method: ConstructionMethod
    bank_ref: EvidenceRef
    bank_split: Literal["train"]


class ExecutionWorkload(Contract):
    """Execute each frozen task once with an explicit policy/input manifest."""

    schema_version: Literal["execution-workload/1"] = "execution-workload/1"
    kind: Literal["execute_tasks"] = "execute_tasks"
    execution_policy_ref: EvidenceRef
    task_inputs_ref: EvidenceRef
    seed: int = Field(ge=0, le=2147483647)


Workload = Annotated[
    ConstructionWorkload | ExecutionWorkload, Field(discriminator="kind")
]


class RunResources(Contract):
    """Frozen runtime configuration; actual loading/paths are checked at bootstrap."""

    schema_version: Literal["run-resources/1"] = "run-resources/1"
    configuration_ref: EvidenceRef
    max_parallel_tasks: int = Field(ge=1, le=900)
    max_actor_generations_per_attempt: int = Field(ge=1, le=10000)
    max_interactions_per_attempt: int = Field(ge=1, le=10000)
    operation_timeout_seconds: int = Field(ge=1, le=86400)
    cleanup_timeout_seconds: int = Field(ge=1, le=3600)


class RoleBudget(Contract):
    schema_version: Literal["role-budget/1"] = "role-budget/1"
    role: Role
    budget_id: Identifier
    reservation_ceiling: Money


class RunBudget(Contract):
    """Same authorization/capacity is shared across runs, never a new local cap."""

    schema_version: Literal["run-budget/2"] = "run-budget/2"
    authorization: BudgetAuthorization
    capacity: BudgetJournalCapacity
    dispatch_policy: BudgetDispatchPolicy
    roles: tuple[RoleBudget, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def valid_role_scopes(self) -> Self:
        if len({item.role for item in self.roles}) != len(self.roles):
            raise ValueError("Paid roles must be unique")
        limits = {
            item.budget_id: item.ceiling.units for item in self.authorization.budgets
        }
        for item in self.roles:
            if (
                item.budget_id not in limits
                or not 0 < item.reservation_ceiling.units <= limits[item.budget_id]
            ):
                raise ValueError(
                    "Paid role needs a positive ceiling within its subbudget"
                )
        BudgetJournalSnapshot(
            capacity=self.capacity,
            dispatch_policy=self.dispatch_policy,
            history=BudgetSnapshot(authorization=self.authorization),
        ).check_capacity()
        return self


class RunPlan(Contract):
    schema_version: Literal["run-plan/3"] = "run-plan/3"
    run_id: Identifier
    release_ref: EvidenceRef
    purpose: Literal["training", "evaluation", "engineering"]
    split: Split
    split_manifest_ref: EvidenceRef
    task_manifest_ref: EvidenceRef
    tasks: tuple[TaskBinding, ...] = Field(min_length=1, max_length=900)
    workload: Workload
    policies: RunPolicies
    models: tuple[RoleModelPlan, ...] = Field(min_length=1, max_length=3)
    resources: RunResources
    run_capacity: JournalCapacity
    budget: RunBudget | None

    @property
    def max_attempts(self) -> int:
        per_task = (
            self.workload.method.max_attempts
            if isinstance(self.workload, ConstructionWorkload)
            else 1
        )
        return len(self.tasks) * per_task

    def request_bounds(self) -> dict[Role, int]:
        bounds: dict[Role, int] = {
            "actor": self.max_attempts
            * self.resources.max_actor_generations_per_attempt
        }
        if isinstance(self.workload, ConstructionWorkload):
            bounds["generator"] = (
                len(self.tasks) * self.workload.method.max_generator_requests
            )
            bounds["teacher"] = len(self.tasks) * self.workload.method.teacher_rounds
        return bounds

    @model_validator(mode="after")
    def coherent_batch(self) -> Self:
        if isinstance(self.workload, ExecutionWorkload) and isinstance(
            self.policies.teacher_template, EnabledPolicy
        ):
            raise ValueError(
                "Teacher template cannot be enabled without Teacher workload"
            )
        if self.release_ref.content_schema != "release-manifest/1":
            raise ValueError("Run must pin a versioned release manifest")
        if any(task.identity.split != self.split for task in self.tasks):
            raise ValueError("All tasks must retain the planned split")
        if len({task.identity.task_id for task in self.tasks}) != len(
            self.tasks
        ) or len({task.identity.source_task_id for task in self.tasks}) != len(
            self.tasks
        ):
            raise ValueError("Task and source identities must be unique within a run")
        if self.purpose == "training" and (
            self.split != "train" or not isinstance(self.workload, ConstructionWorkload)
        ):
            raise ValueError("Training targets require train construction workload")
        if self.purpose == "evaluation" and not isinstance(
            self.workload, ExecutionWorkload
        ):
            raise ValueError("Evaluation cannot perform Teacher target construction")
        if isinstance(self.workload, ConstructionWorkload) and self.split != "train":
            raise ValueError("Construction cannot consume test/dev feedback")
        if self.resources.max_parallel_tasks > len(self.tasks):
            raise ValueError("Parallel task limit exceeds the declared batch")
        if self.run_capacity.max_attempts != self.max_attempts:
            raise ValueError("Run capacity must match the derived attempt schedule")
        bounds = self.request_bounds()
        if len({model.role for model in self.models}) != len(self.models) or {
            model.role for model in self.models
        } != set(bounds):
            raise ValueError("Models must exactly cover the workload roles")
        paid = {model.role for model in self.models if model.paid}
        if not paid:
            if self.budget is not None:
                raise ValueError("Local inference does not create a paid ledger")
        elif self.budget is None or {item.role for item in self.budget.roles} != paid:
            raise ValueError("Every and only paid role needs a budget binding")
        elif sum(bounds[role] for role in paid) > self.budget.capacity.max_requests:
            raise ValueError("Shared request capacity cannot fit this batch")
        if self.budget is not None:
            amounts: dict[str, int] = {}
            for item in self.budget.roles:
                amounts[item.budget_id] = (
                    amounts.get(item.budget_id, 0)
                    + bounds[item.role] * item.reservation_ceiling.units
                )
            if sum(amounts.values()) > self.budget.authorization.ceiling.units or any(
                amounts.get(limit.budget_id, 0) > limit.ceiling.units
                for limit in self.budget.authorization.budgets
            ):
                raise ValueError(
                    "Worst-case batch reservations exceed frozen authorization"
                )
        return self

    def references(self) -> tuple[EvidenceRef, ...]:
        """Full direct immutable inputs; semantic transitive closure is separate."""
        refs = [
            self.release_ref,
            self.split_manifest_ref,
            self.task_manifest_ref,
            self.resources.configuration_ref,
        ]
        refs.extend(self.policies.references())
        for task in self.tasks:
            refs.extend(
                (task.public_task_ref, task.private_spec_ref, task.baseline_ref)
            )
        for model in self.models:
            refs.extend((model.model_binding_ref, model.parameters_ref))
        if isinstance(self.workload, ConstructionWorkload):
            refs.append(self.workload.bank_ref)
        else:
            refs.extend(
                (self.workload.execution_policy_ref, self.workload.task_inputs_ref)
            )
        if self.budget is not None:
            refs.append(self.budget.authorization.authorization_ref)
        return tuple(dict.fromkeys(refs))

    def check_binding(self, binding: RunBinding) -> None:
        """Consumer validates exact envelope before creating any runtime journal."""
        if (
            binding.owner.run_id != self.run_id
            or binding.release_ref != self.release_ref
        ):
            raise ValueError("Run binding differs from its frozen plan")
        if (
            binding.plan_ref.content_schema != self.schema_version
            or binding.plan_ref.visibility != "private"
        ):
            raise ValueError("RunPlan must be a private, versioned payload")
        shell = {
            "schema_version": "run-journal-snapshot/2",
            "binding": binding.model_dump(mode="json"),
            "capacity": self.run_capacity.model_dump(mode="json"),
            "entries": [],
        }
        self.run_capacity.preflight(
            len(json.dumps(shell, ensure_ascii=False, separators=(",", ":")).encode())
        )

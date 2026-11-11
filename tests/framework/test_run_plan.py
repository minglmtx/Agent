"""Frozen task batch inputs, exact bounds and method compatibility variants."""

import json
from typing import cast

import pytest
from pydantic import ValidationError

from lab_generate_skill.domain.budget import BudgetAuthorization, BudgetLimit, Money
from lab_generate_skill.domain.budget_policy import BudgetDispatchPolicy
from lab_generate_skill.domain.budget_journal import BudgetJournalCapacity
from lab_generate_skill.domain.construction_method import ConstructionMethod
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.journal_capacity import JournalCapacity
from lab_generate_skill.domain.lifecycle import ResourceOwner
from lab_generate_skill.domain.optional_policies import InactivePolicy, RunPolicies
from lab_generate_skill.domain.run_plan import (
    ConstructionWorkload,
    ExecutionWorkload,
    RoleBudget,
    Role,
    RoleModelPlan,
    RunBudget,
    RunPlan,
    RunResources,
)
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.errors import JournalCapacityExceeded


def reference(schema: str = "fixture/1", public: bool = False) -> EvidenceRef:
    return EvidenceRef(
        uri="cas://sha256/" + "a" * 64,
        sha256="a" * 64,
        size_bytes=1,
        media_type="application/json",
        content_schema=schema,
        visibility="public" if public else "private",
        producer="unit-fixture",
    )


def method() -> ConstructionMethod:
    return ConstructionMethod(
        candidates=4,
        top_k=6,
        duplicate_resamples=4,
        teacher_rounds=3,
        seed=42,
        generator_temperatures=(0.7, 0.8, 0.9, 1.0, 1.1),
        first_teacher_required=True,
        selection_metric="recorded_environment_step_returns_v1",
    )


def plan() -> RunPlan:
    task = TaskBinding(
        identity=TaskIdentity(
            source_task_id="source",
            task_id="task",
            split="train",
            site="map",
            family="export",
            contract_version=1,
        ),
        registration_id="map-export-1",
        public_task_ref=reference("public-task/1", True),
        private_spec_ref=reference(),
        baseline_ref=reference(),
    )
    authorization = BudgetAuthorization(
        authorization_id="unit-auth",
        authorization_ref=reference(),
        ceiling=Money(units=30),
        budgets=(BudgetLimit(budget_id="teacher", ceiling=Money(units=30)),),
    )
    return RunPlan(
        run_id="run",
        release_ref=reference("release-manifest/1"),
        purpose="training",
        split="train",
        split_manifest_ref=reference("data-split/1"),
        task_manifest_ref=reference(),
        tasks=(task,),
        workload=ConstructionWorkload(
            method=method(), bank_ref=reference("bank-manifest/1"), bank_split="train"
        ),
        policies=RunPolicies(
            actor_memory=InactivePolicy(
                status="disabled", reason="unit baseline without memory optimization"
            ),
            teacher_template=InactivePolicy(
                status="disabled", reason="unit baseline Teacher format"
            ),
        ),
        models=tuple(
            RoleModelPlan(
                role=cast(Role, role),
                provider="fixture",
                model="fixture/model",
                model_binding_ref=reference(),
                parameters_ref=reference(),
                paid=role == "teacher",
            )
            for role in ("actor", "generator", "teacher")
        ),
        resources=RunResources(
            configuration_ref=reference(),
            max_parallel_tasks=1,
            max_actor_generations_per_attempt=20,
            max_interactions_per_attempt=16,
            operation_timeout_seconds=600,
            cleanup_timeout_seconds=60,
        ),
        run_capacity=JournalCapacity(
            max_attempts=7, max_entries=100, max_bytes=1024 * 1024, max_entry_bytes=8192
        ),
        budget=RunBudget(
            dispatch_policy=BudgetDispatchPolicy(max_unsettled_dispatches=1),
            authorization=authorization,
            capacity=BudgetJournalCapacity(
                max_requests=3,
                max_entries=12,
                max_bytes=512 * 1024,
                max_entry_bytes=8192,
            ),
            roles=(
                RoleBudget(
                    role="teacher",
                    budget_id="teacher",
                    reservation_ceiling=Money(units=10),
                ),
            ),
        ),
    )


def binding(value: RunPlan) -> RunBinding:
    return RunBinding(
        owner=ResourceOwner(
            run_id=value.run_id,
            owner_id="owner",
            job_id="controller",
            worker_id="worker",
        ),
        plan_ref=reference("run-plan/3"),
        release_ref=value.release_ref,
        submission_key="submission",
    )


def test_method_schedule_matches_existing_semantics() -> None:
    value = method()
    for candidate in range(4):
        for retry in range(5):
            seed, temperature = value.generator_sampling(candidate, retry)
            assert seed == 42 + candidate + 4 * retry
            assert temperature == pytest.approx(min(1.2, 0.7 + 0.1 * retry))
    assert [value.teacher_seed(i) for i in (1, 2, 3)] == [42, 43, 44]
    assert value.max_attempts == 7 and value.max_generator_requests == 20
    assert ConstructionMethod.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize(
    "candidate,retry",
    [(-1, 0), (4, 0), (0, -1), (0, 5), (True, 0), (0, False), ("0", 0), (0, None)],
)
def test_invalid_generator_indices(candidate: object, retry: object) -> None:
    with pytest.raises(ValueError):
        method().generator_sampling(cast(int, candidate), cast(int, retry))


@pytest.mark.parametrize("index", [0, 4, -1, True, "1", None, 1.0])
def test_invalid_teacher_indices(index: object) -> None:
    with pytest.raises(ValueError):
        method().teacher_seed(cast(int, index))


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidates", 4.0),
        ("top_k", True),
        ("duplicate_resamples", 5),
        ("teacher_rounds", 0),
        ("first_teacher_required", 1),
        ("first_teacher_required", False),
        ("seed", 2147483629),
        ("seed", -1),
        ("seed", True),
        ("selection_metric", "generation_count"),
        ("generator_temperatures", (0.7, 0.8, 0.9, 1.0)),
        ("generator_temperatures", (float("nan"), 0.8, 0.9, 1.0, 1.1)),
        ("generator_temperatures", (float("inf"), 0.8, 0.9, 1.0, 1.1)),
        ("generator_temperatures", (0.5, 0.8, 0.9, 1.0, 1.1)),
    ],
)
def test_invalid_method(field: str, value: object) -> None:
    data = method().model_dump(mode="python")
    data[field] = value
    with pytest.raises(ValidationError):
        ConstructionMethod.model_validate(data)


def test_plan_roundtrip_counts_and_binding() -> None:
    value = plan()
    assert value.max_attempts == 7
    assert value.request_bounds() == {"actor": 140, "generator": 20, "teacher": 3}
    assert RunPlan.model_validate_json(value.model_dump_json()) == value
    value.check_binding(binding(value))
    assert value.release_ref in value.references()
    assert len(value.references()) == len(set(value.references()))
    with pytest.raises(ValidationError):
        setattr(value, "run_id", "changed")


def test_local_evaluation_has_no_paid_budget() -> None:
    value = plan()
    fields = value.model_dump(mode="python")
    fields.update(
        purpose="evaluation",
        workload=ExecutionWorkload(
            execution_policy_ref=reference(), task_inputs_ref=reference(), seed=7
        ),
        models=(value.models[0],),
        budget=None,
        run_capacity=JournalCapacity(
            max_attempts=1, max_entries=20, max_bytes=512 * 1024, max_entry_bytes=8192
        ),
    )
    evaluation = RunPlan.model_validate(fields)
    assert evaluation.max_attempts == 1 and evaluation.request_bounds() == {"actor": 20}
    evaluation.check_binding(binding(evaluation))


@pytest.mark.parametrize(
    "field,value",
    [
        ("tasks", ()),
        ("tasks", []),
        ("budget", None),
        ("purpose", "evaluation"),
        ("purpose", "other"),
        ("release_ref", reference()),
        ("models", ()),
        ("split", "test"),
        ("run_id", None),
        ("unknown_field", True),
    ],
)
def test_invalid_plan_top_level(field: str, value: object) -> None:
    data = plan().model_dump(mode="python")
    data[field] = value
    with pytest.raises(ValidationError):
        RunPlan.model_validate(data)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_task",
        "duplicate_source",
        "duplicate_role",
        "missing_role",
        "local_paid_budget",
        "wrong_budget_role",
        "wrong_subbudget",
        "zero_reservation",
        "oversized_reservation",
        "batch_exceeds_money",
        "insufficient_requests",
        "wrong_attempt_count",
        "too_parallel",
        "bad_timeout",
        "test_construction",
    ],
)
def test_cross_field_rejection(mutation: str) -> None:
    fields = plan().model_dump(mode="json")
    if mutation == "duplicate_task":
        fields["tasks"].append(dict(fields["tasks"][0]))
    elif mutation == "duplicate_source":
        duplicate = json.loads(json.dumps(fields["tasks"][0]))
        duplicate["identity"]["task_id"] = "other"
        fields["tasks"].append(duplicate)
    elif mutation == "duplicate_role":
        fields["models"][1]["role"] = "actor"
    elif mutation == "missing_role":
        fields["models"].pop()
    elif mutation == "local_paid_budget":
        fields["models"][2]["paid"] = False
    elif mutation == "wrong_budget_role":
        fields["budget"]["roles"][0]["role"] = "actor"
    elif mutation == "wrong_subbudget":
        fields["budget"]["roles"][0]["budget_id"] = "missing"
    elif mutation == "zero_reservation":
        fields["budget"]["roles"][0]["reservation_ceiling"]["units"] = 0
    elif mutation == "oversized_reservation":
        fields["budget"]["roles"][0]["reservation_ceiling"]["units"] = 31
    elif mutation == "batch_exceeds_money":
        fields["budget"]["roles"][0]["reservation_ceiling"]["units"] = 11
    elif mutation == "insufficient_requests":
        fields["budget"]["capacity"]["max_requests"] = 2
    elif mutation == "wrong_attempt_count":
        fields["run_capacity"]["max_attempts"] = 6
    elif mutation == "too_parallel":
        fields["resources"]["max_parallel_tasks"] = 2
    elif mutation == "bad_timeout":
        fields["resources"]["cleanup_timeout_seconds"] = 0
    elif mutation == "test_construction":
        fields["purpose"] = "engineering"
        fields["split"] = "test"
        fields["tasks"][0]["identity"]["split"] = "test"
    with pytest.raises(ValidationError):
        RunPlan.model_validate_json(json.dumps(fields))


def test_binding_identity_and_actual_envelope_capacity() -> None:
    value = plan()
    original = binding(value)
    for update in (
        {"release_ref": reference("other")},
        {"plan_ref": reference("wrong")},
        {"owner": original.owner.model_copy(update={"run_id": "other"})},
    ):
        changed = RunBinding.model_validate(original.model_copy(update=update))
        with pytest.raises(ValueError):
            value.check_binding(changed)
    fields = value.model_dump(mode="python")
    fields["run_capacity"] = JournalCapacity(
        max_attempts=7, max_entries=86, max_bytes=86 * 8193, max_entry_bytes=8192
    )
    tight = RunPlan.model_validate(fields)
    with pytest.raises(JournalCapacityExceeded):
        tight.check_binding(binding(tight))


def test_seed_upper_boundary_and_repeated_sampling() -> None:
    values = method().model_dump(mode="python")
    values["seed"] = 2147483628
    upper = ConstructionMethod.model_validate(values)
    assert upper.generator_sampling(3, 4)[0] == 2147483647
    assert upper.generator_sampling(3, 4) == upper.generator_sampling(3, 4)


def test_three_task_batch_derives_all_capacity() -> None:
    fields = plan().model_dump(mode="json")
    original = fields["tasks"][0]
    fields["tasks"] = []
    for index in range(3):
        task = json.loads(json.dumps(original))
        task["identity"]["task_id"] = f"task-{index}"
        task["identity"]["source_task_id"] = f"source-{index}"
        fields["tasks"].append(task)
    fields["resources"]["max_parallel_tasks"] = 3
    fields["run_capacity"].update(
        max_attempts=21, max_entries=240, max_bytes=4 * 1024 * 1024
    )
    fields["budget"]["authorization"]["ceiling"]["units"] = 90
    fields["budget"]["authorization"]["budgets"][0]["ceiling"]["units"] = 90
    fields["budget"]["capacity"].update(max_requests=9, max_entries=36)
    batch = RunPlan.model_validate_json(json.dumps(fields))
    assert batch.max_attempts == 21
    assert batch.request_bounds() == {"actor": 420, "generator": 60, "teacher": 9}
    batch.check_binding(binding(batch))


@pytest.mark.parametrize("ceiling,passes", [(170, True), (169, False)])
def test_two_paid_roles_share_one_subbudget(ceiling: int, passes: bool) -> None:
    fields = plan().model_dump(mode="json")
    fields["models"][0]["paid"] = True
    fields["budget"]["roles"].append(
        {
            "schema_version": "role-budget/1",
            "role": "actor",
            "budget_id": "teacher",
            "reservation_ceiling": Money(units=1).model_dump(mode="json"),
        }
    )
    fields["budget"]["authorization"]["ceiling"]["units"] = 170
    fields["budget"]["authorization"]["budgets"][0]["ceiling"]["units"] = ceiling
    fields["budget"]["capacity"].update(
        max_requests=143, max_entries=572, max_bytes=8 * 1024 * 1024
    )
    if passes:
        value = RunPlan.model_validate_json(json.dumps(fields))
        assert value.budget is not None and len(value.budget.roles) == 2
    else:
        with pytest.raises(ValidationError, match="Worst-case batch"):
            RunPlan.model_validate_json(json.dumps(fields))


def test_local_construction_cannot_create_budget_history() -> None:
    fields = plan().model_dump(mode="json")
    for model in fields["models"]:
        model["paid"] = False
    fields["budget"] = None
    value = RunPlan.model_validate_json(json.dumps(fields))
    assert value.budget is None and value.max_attempts == 7


@pytest.mark.parametrize("split", ["dev", "test"])
def test_evaluation_retains_split_without_teacher(split: str) -> None:
    fields = plan().model_dump(mode="json")
    fields.update(
        purpose="evaluation",
        split=split,
        budget=None,
        workload=ExecutionWorkload(
            execution_policy_ref=reference(), task_inputs_ref=reference(), seed=42
        ).model_dump(mode="json"),
    )
    fields["tasks"][0]["identity"]["split"] = split
    fields["models"] = fields["models"][:1]
    fields["run_capacity"]["max_attempts"] = 1
    assert RunPlan.model_validate_json(json.dumps(fields)).split == split

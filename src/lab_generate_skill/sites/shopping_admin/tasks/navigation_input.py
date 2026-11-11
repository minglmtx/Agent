"""Bind exact selected71 native shape; no historical status grants permission."""

from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from .navigation_spec import AdminNavigationSpec, AdminNavigationInputs

ROOT_KEYS = {
    "evaluator_version",
    "goal",
    "kind",
    "not_formal_training_admission",
    "public_completion_requirement",
    "public_completion_version",
    "runtime_task_id",
    "scope_id",
    "source_task_id",
    "spec",
    "start_path",
    "status",
    "task_revision",
}
SPEC_KEYS = {
    "heading",
    "initialization",
    "kind",
    "label",
    "protocol",
    "start_path",
    "target_path",
}
REVISION_KEYS = {
    "version",
    "source_task_id",
    "source_goal",
    "runtime_goal",
    "previous_revision",
    "reason",
    "contains_reference_answer",
    "contains_action_sequence",
}


def declare_admin_navigation(
    native: dict[str, Any], reference: EvidenceRef, task: TaskIdentity, goal: str
) -> AdminNavigationSpec:
    """Validate original group fields before an allocated public URL exists.

    The adapter verifies bounded bytes and strict JSON before this site binder;
    no owner, token, endpoint, source or permission is manufactured here. The
    original dynamic binder below consumes this same unadmitted declaration.
    """
    reference = EvidenceRef.model_validate(reference)
    task = TaskIdentity.model_validate(task)
    if type(native) is not dict:
        raise ValueError("Original native object required")
    spec, revision = native.get("spec"), native.get("task_revision")
    if (
        set(native) != ROOT_KEYS
        or type(spec) is not dict
        or set(spec) != SPEC_KEYS
        or type(revision) is not dict
        or set(revision) != REVISION_KEYS
    ):
        raise ValueError(
            "Unsupported original Admin navigation shape; select its actual branch"
        )
    if (
        native["kind"],
        native["evaluator_version"],
        native["status"],
        native["not_formal_training_admission"],
        native["public_completion_version"],
    ) != (
        "derived",
        "admin-page-navigation-v1",
        "ready_for_single_attempt",
        True,
        "admin-public-completion-v1",
    ) or native[
        "not_formal_training_admission"
    ] is not True:
        raise ValueError("Original explicitly unadmitted derived navigation required")
    if (spec["kind"], spec["protocol"]) != (
        "page_navigation",
        "admin-page-navigation-v1",
    ) or spec["initialization"] not in (
        "fixed_local_start_not_original_trajectory_start",
        "declared_local_start; original goal unchanged",
    ):
        raise ValueError("Unsupported original navigation initialization/protocol")
    if (
        type(native["scope_id"]) is not int
        or native["scope_id"] != 0
        or any(
            type(native[k]) is not str or not native[k].strip()
            for k in (
                "source_task_id",
                "runtime_task_id",
                "goal",
                "start_path",
                "public_completion_requirement",
            )
        )
    ):
        raise ValueError("Original navigation identifiers/public fields required")
    if (native["source_task_id"], native["goal"], native["start_path"]) != (
        task.source_task_id,
        goal,
        spec["start_path"],
    ):
        raise ValueError(
            "Current public identity/goal/start changed original native fields"
        )
    if (
        (revision["version"], revision["source_task_id"], revision["runtime_goal"])
        != ("admin-public-completion-v1", native["source_task_id"], goal)
        or revision["contains_reference_answer"] is not False
        or revision["contains_action_sequence"] is not False
        or revision["previous_revision"] is not None
        or any(
            type(revision[k]) is not str or not revision[k].strip()
            for k in ("source_goal", "reason")
        )
    ):
        raise ValueError("Original declared public completion revision required")
    return AdminNavigationSpec(
        task=task,
        native_contract_ref=reference,
        legacy_runtime_task_id=native["runtime_task_id"],
        store_id=native["scope_id"],
        start_path=spec["start_path"],
        target_path=spec["target_path"],
        heading=spec["heading"],
        label=spec["label"],
        initialization=spec["initialization"],
    )


def bind_admin_navigation(
    native: dict[str, Any], reference: EvidenceRef, public: PublicTask
) -> AdminNavigationInputs:
    """Join the original static declaration to the actual allocated public URL."""
    public = PublicTask.model_validate(public)
    private = declare_admin_navigation(native, reference, public.identity, public.goal)
    start = urlsplit(public.start_url)
    if (
        start.scheme != "http"
        or start.hostname not in ("127.0.0.1", "localhost")
        or start.port is None
        or not 1024 <= start.port <= 65535
        or start.username is not None
        or start.password is not None
        or start.query
        or start.fragment
        or start.path != "/admin" + private.start_path
    ):
        raise ValueError("Actual allocated local Admin start URL required")
    return AdminNavigationInputs(public_task=public, private_spec=private)

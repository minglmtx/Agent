"""Selected original contract to explicit public task and private requirements."""

from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from .group_spec import GroupRequirements, GroupSpec

NATIVE_FIELDS = frozenset(
    {
        "task_id",
        "source_task_id",
        "domain",
        "goal",
        "start_path",
        "recorded_start_paths",
        "source_trace_ids",
        "group_creation",
        "heldout_quarantine",
        "eligible_for_training",
        "task_text_changed",
        "status",
        "api_calls",
        "completion_scope",
        "admission_result",
    }
)


def bind_group_inputs(
    native: dict[str, Any], reference: EvidenceRef, public: PublicTask
) -> GroupSpec:
    public = PublicTask.model_validate(public)
    if (
        type(native) is not dict
        or set(native) != NATIVE_FIELDS
        or native.get("domain") != "gitlab"
    ):
        raise ValueError("Unsupported original GitLab group contract fields")
    if any(
        native.get(key) is not False
        for key in ("heldout_quarantine", "eligible_for_training", "task_text_changed")
    ):
        raise ValueError("Original group contract scope or goal revision differs")
    if (
        native.get("status") != "draft_requires_two_live_controls"
        or type(native.get("api_calls")) is not int
        or native["api_calls"] != 0
    ):
        raise ValueError(
            "Original contract does not grant execution or training admission"
        )
    if (native.get("source_task_id"), native.get("task_id")) != (
        public.identity.source_task_id,
        public.identity.task_id,
    ):
        raise ValueError("Original group task lineage differs")
    if (
        public.goal != native.get("goal")
        or "send_msg_to_user" not in public.allowed_actions
    ):
        raise ValueError(
            "Original public group goal and explicit terminal action required"
        )
    start, recorded = native.get("start_path"), native.get("recorded_start_paths")
    starts = {"/", "/groups/new", "/groups/new#create-group-pane"}
    if (
        type(start) is not str
        or start not in starts
        or type(recorded) is not list
        or not recorded
        or any(type(path) is not str or path not in starts for path in recorded)
        or len(set(recorded)) != len(recorded)
        or start not in recorded
    ):
        raise ValueError("Explicit recorded original group start required")
    paths = native.get("source_trace_ids")
    if (
        type(paths) is not list
        or not paths
        or any(type(item) is not str or not item.strip() for item in paths)
    ):
        raise ValueError("Original group source traces required")
    for key in ("completion_scope", "admission_result"):
        if type(native[key]) is not str or not native[key].strip():
            raise ValueError("Original private group scope lineage required")
    try:
        url = urlsplit(public.start_url)
        valid = (url.scheme, url.hostname, url.path) == (
            "http",
            "127.0.0.1",
            urlsplit(start).path,
        ) and (
            url.port is not None
            and 1024 <= url.port <= 65535
            and url.username is None
            and url.password is None
            and not url.query
            and url.fragment == urlsplit(start).fragment
            and public.start_url == f"http://127.0.0.1:{url.port}" + start
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Allocated original private GitLab group URL required")
    return GroupSpec(
        task=public.identity,
        native_contract_ref=reference,
        native_goal=native["goal"],
        requirements=GroupRequirements.model_validate(native["group_creation"]),
    )

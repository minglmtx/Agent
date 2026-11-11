"""Bind original bytes to an explicit public task; never initialize or admit."""

from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from .ssh_key_parameters import SshKeyParameters, render_public_goal
from .ssh_key_spec import SshKeyInputs, SshKeySpec, OUTPUT_REQUIREMENTS

NATIVE_FIELDS = frozenset(
    {
        "source_task_id",
        "task_id",
        "domain",
        "original_goal",
        "goal",
        "start_path",
        "recorded_start_urls",
        "recorded_start_paths",
        "source_trace_ids",
        "task_text_changed",
        "goal_revision",
        "start_revision",
        "heldout_quarantine",
        "eligible_for_training",
        "public_parameters",
        "public_task_input",
        "gitlab_public_bridge",
        "completion",
        "is_explicit_derivative",
        "original_benchmark_equivalence",
    }
)


def _object(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("Expected exact native GitLab object")
    return value


def bind_ssh_key_inputs(
    native: dict[str, Any], reference: EvidenceRef, public: PublicTask
) -> SshKeyInputs:
    public = PublicTask.model_validate(public)
    native = _object(native)
    if set(native) != NATIVE_FIELDS or native.get("domain") != "gitlab":
        raise ValueError("Unsupported original GitLab SSH-key fields")
    for key, expected in (
        ("heldout_quarantine", False),
        ("eligible_for_training", False),
        ("is_explicit_derivative", True),
        ("original_benchmark_equivalence", False),
        ("task_text_changed", True),
    ):
        if native.get(key) is not expected:
            raise ValueError("GitLab historical scope flag differs: " + key)
    parameters = SshKeyParameters.model_validate(
        _object(native.get("public_parameters"))
    )
    if (
        native.get("public_task_input")
        != {
            "goal": native.get("goal"),
            "public_parameters": parameters.model_dump(),
        }
        or native.get("gitlab_public_bridge")
        != {
            "version": "gitlab-public-bridge-runtime-candidate-v1",
            "kind": "native_profile_ssh_key",
            "declaration": parameters.model_dump(),
        }
        or native.get("completion") != {"family": "gitlab_public_bridge"}
    ):
        raise ValueError("Exact supplied public SSH parameters and protocol required")
    revision = _object(native.get("goal_revision"))
    if (
        set(revision)
        != {
            "version",
            "original_goal",
            "derived_goal",
            "reason",
            "equivalent_to_original_goal",
        }
        or revision.get("version") != "public-cpu-candidate-v1"
        or (
            revision.get("original_goal") != native.get("original_goal")
            or revision.get("derived_goal") != native.get("goal")
            or revision.get("equivalent_to_original_goal") is not False
            or not isinstance(revision.get("reason"), str)
            or not revision["reason"].strip()
            or not isinstance(native.get("original_goal"), str)
            or not native["original_goal"].strip()
        )
    ):
        raise ValueError("Original GitLab goal lineage differs")
    paths, urls, traces = (
        native.get(k)
        for k in ("recorded_start_paths", "recorded_start_urls", "source_trace_ids")
    )
    if (
        native.get("start_path") != "/"
        or native.get("start_revision") is not None
        or (
            type(paths) is not list
            or not paths
            or paths[0] != "/"
            or type(urls) is not list
            or len(urls) != len(paths)
            or type(traces) is not list
            or not traces
            or any(type(x) is not str or not x.strip() for x in traces)
        )
    ):
        raise ValueError("Original GitLab start/trace lineage required")
    for path, recorded in zip(paths, urls, strict=True):
        if (
            type(path) is not str
            or not path.startswith("/")
            or path.startswith("//")
            or (
                type(recorded) is not str
                or "\\" in recorded
                or any(ord(c) < 32 for c in recorded)
            )
        ):
            raise ValueError("Invalid original GitLab start declaration")
        old = urlsplit(recorded)
        if (
            old.scheme != "http"
            or not old.netloc
            or old.path != path
            or (
                old.username is not None
                or old.password is not None
                or old.query
                or old.fragment
            )
        ):
            raise ValueError("Original GitLab recorded URL/path differs")
    url = urlsplit(public.start_url)
    if (url.scheme, url.hostname, url.path) != ("http", "127.0.0.1", "/") or (
        url.port is None
        or not 1024 <= url.port <= 65535
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
    ):
        raise ValueError("Explicit GitLab start requires its allocated local root")
    if native.get("source_task_id") != public.identity.source_task_id or (
        "send_msg_to_user" not in public.allowed_actions
        or not all(x in public.output_requirements for x in OUTPUT_REQUIREMENTS)
    ):
        raise ValueError("Original source and declared terminal protocol required")
    private = SshKeySpec(
        task=public.identity,
        native_contract_ref=reference,
        legacy_runtime_task_id=native["task_id"],
        native_goal=native["goal"],
        parameters=parameters,
    )
    if public.goal != render_public_goal(private.native_goal, parameters):
        raise ValueError(
            "Explicit public task must include original supplied key/title"
        )
    return SshKeyInputs(public_task=public, private_spec=private)

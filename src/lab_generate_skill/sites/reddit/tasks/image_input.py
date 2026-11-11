"""Bind the reviewed native declaration to explicitly approved public inputs."""

from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from .image_parameters import ImageParameters
from .image_contract_variant import input_variant
from .image_spec import NativeImageSpec, NativeImageInputs, OUTPUT_REQUIREMENTS

NATIVE_FIELDS = frozenset(
    {
        "actor_attempts",
        "actor_retry_authorized",
        "api_calls",
        "controls_verified",
        "cpu_repair_only",
        "domain",
        "driver_key",
        "eligible_for_training",
        "environment_revision",
        "family",
        "goal",
        "goal_revision",
        "heldout_quarantine",
        "kind",
        "missing_gate",
        "normal_gate_passed",
        "normal_verified",
        "original_alias_ids",
        "original_candidate_strict_unclaimed_new_source",
        "original_evaluation_equivalence",
        "original_goal",
        "private_reference_is_actor_input",
        "public_parameters",
        "public_parameters_must_reach_generator_and_actor",
        "ready_for_normal_cpu_submission",
        "recorded_start_paths",
        "recorded_start_urls",
        "recorded_trace_evidence",
        "source_task_id",
        "source_trace_ids",
        "start_path",
        "start_revision",
        "strict_unclaimed_new_source",
        "task_id",
        "task_text_changed",
        "training_admitted",
        "admission_result",
    }
)


def bind_image_inputs(
    native: dict[str, Any], reference: EvidenceRef, public: PublicTask
) -> NativeImageInputs:
    public = PublicTask.model_validate(public)
    if type(native) is not dict:
        raise TypeError("Original native image declaration must be an object")
    path, goal_version = input_variant(native, reference)
    fields = NATIVE_FIELDS | ({"object_resolution"} if path == "/forums/all" else set())
    if set(native) != fields:
        raise ValueError("Exact original native image contract fields required")
    if (native["domain"], native["family"], native["kind"], native["driver_key"]) != (
        "reddit",
        "reddit_native_media_candidate",
        "native_image_submission",
        "reddit-native-media-cpu-v1",
    ):
        raise ValueError("Original selected native-media driver required")
    for name, expected in (
        ("eligible_for_training", False),
        ("heldout_quarantine", False),
        ("private_reference_is_actor_input", False),
        ("original_evaluation_equivalence", False),
        ("training_admitted", False),
        ("normal_verified", False),
        ("normal_gate_passed", False),
        ("public_parameters_must_reach_generator_and_actor", True),
        ("task_text_changed", True),
    ):
        if native[name] is not expected:
            raise ValueError("Original native-media scope flag differs: " + name)
    revision = native["goal_revision"]
    if (
        type(revision) is not dict
        or revision
        != dict(
            version=goal_version,
            original_goal=native["original_goal"],
            derived_goal=native["goal"],
            equivalent_to_original_goal=False,
            reason=revision.get("reason"),
        )
        or (
            type(revision.get("reason")) is not str
            or not revision["reason"].strip()
            or type(native["original_goal"]) is not str
            or not native["original_goal"].strip()
        )
    ):
        raise ValueError("Original native-media goal lineage required")
    paths, urls, traces = (
        native[k]
        for k in ("recorded_start_paths", "recorded_start_urls", "source_trace_ids")
    )
    if (
        native["start_path"] != path
        or native["start_revision"] is not None
        or (
            type(paths) is not list
            or not paths
            or any(p != path for p in paths)
            or type(urls) is not list
            or len(urls) != len(paths)
            or type(traces) is not list
            or not traces
            or any(type(t) is not str or not t.strip() for t in traces)
        )
    ):
        raise ValueError(
            "Original native-image submit start and trace lineage required"
        )
    for value in urls:
        if type(value) is not str or "\\" in value or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid original recorded media URL")
        old = urlsplit(value)
        if (
            old.scheme != "http"
            or not old.netloc
            or old.path != path
            or old.username is not None
            or old.password is not None
            or old.query
            or old.fragment
        ):
            raise ValueError("Original recorded native-media start differs")
    parsed = urlsplit(public.start_url)
    if (parsed.scheme, parsed.hostname, parsed.path) != (
        "http",
        "127.0.0.1",
        path,
    ) or (
        parsed.port is None
        or not 1024 <= parsed.port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Allocated original local submit page required")
    if native["source_task_id"] != public.identity.source_task_id or (
        not {"upload_file", "send_msg_to_user"} <= set(public.allowed_actions)
        or not all(v in public.output_requirements for v in OUTPUT_REQUIREMENTS)
    ):
        raise ValueError(
            "Original source and explicit upload/completion protocol required"
        )
    spec = NativeImageSpec(
        task=public.identity,
        native_contract_ref=reference,
        legacy_runtime_task_id=native["task_id"],
        native_goal=native["goal"],
        parameters=ImageParameters.model_validate(native["public_parameters"]),
    )
    return NativeImageInputs(public_task=public, private_spec=spec)

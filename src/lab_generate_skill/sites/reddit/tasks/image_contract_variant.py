"""Exact recorded v2 forum resolution; original v1 declarations remain separate."""

from typing import Any
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.reddit_image_start import FORUM_DIRECTORY_SOURCE

FORUM_CONTRACT_SHA256 = (
    "4306fa4c04813e233ab7265032b6bbd357717a7b9fe8f05c0f0bc13d3295e10a"
)


def input_variant(native: dict[str, Any], reference: EvidenceRef) -> tuple[str, str]:
    if "object_resolution" not in native:
        if native.get("source_task_id") == FORUM_DIRECTORY_SOURCE:
            raise ValueError(
                "Selected forum-directory source requires its original v2 declaration"
            )
        return "/submit", "native-media-cpu-v1"
    traces = ["gobrowse:24334", "gobrowse:24335"]
    if (
        reference.sha256 != FORUM_CONTRACT_SHA256
        or native.get("source_task_id") != FORUM_DIRECTORY_SOURCE
        or native.get("source_trace_ids") != traces
        or native.get("object_resolution")
        != dict(
            explicit_training_derivative=True,
            original_phrase="the photography forum",
            original_trace_ids=traces,
            recorded_public_paths=["/f/EarthPorn", "/submit/EarthPorn"],
            resolved_forum="EarthPorn",
            uses_late_actor_to_reinterpret_original=False,
            uses_outcome_label=False,
            version="recorded-native-public-forum-v1",
        )
        or native.get("recorded_trace_evidence")
        != [
            dict(
                line_number=967,
                line_sha256="143f99030a080d967e30133998b0f9110f9d3e0286e1f9f9d8c5ca7ebf860cc3",
                trace_id="gobrowse:24335",
            ),
            dict(
                line_number=968,
                line_sha256="10ec5e43cb7a81ead56fe6505f6197491ecbbfb82905469ff1cf3594ea01468e",
                trace_id="gobrowse:24334",
            ),
        ]
    ):
        raise ValueError(
            "Original pinned forum-resolution contract and both trace bindings required"
        )
    return "/forums/all", "native-media-explicit-existing-forum-v2"

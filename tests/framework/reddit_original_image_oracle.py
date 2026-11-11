"""Audit only: exact capsule-pinned pure guards, no old runtime imports/effects."""

import ast
from datetime import datetime
import hashlib
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any, Callable
from uuid import UUID
import json
from lab_generate_skill.sites.reddit.tasks.image_parameters import PHOTOS
from lab_generate_skill.domain.evidence import EvidenceRef

ROOT = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/sft-reddit-native-media-formal-integration-v1"
)
CAPSULE_SHA = "46263ad133046815b755b764aebdb9d82b7ef5d10f663912804f14fa70373c15"


def oracle() -> Callable[[dict[str, Any], dict[str, Any]], bool]:
    raw = (ROOT / "runtime/capsule.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != CAPSULE_SHA:
        raise ValueError("Original selected media capsule changed")
    capsule = json.loads(raw)
    namespace: dict[str, Any] = {
        "re": re,
        "hashlib": hashlib,
        "UUID": UUID,
        "datetime": datetime,
        "SHA": re.compile("[0-9a-f]{64}"),
        "MD5": re.compile("[0-9a-f]{32}"),
        "protection": SimpleNamespace(VERSION="reddit45-readonly-complete13-v1"),
        "NATIVE13": {
            "forums",
            "comments",
            "submission_votes",
            "comment_votes",
            "wiki_pages",
            "wiki_revisions",
            "forum_tags",
            "forums_tags",
            "hidden_forums",
            "forum_subscriptions",
            "user_blocks",
            "users",
            "submissions",
        },
    }
    for path, names in [
        ("src/lab_generate_skill/reddit_protected_chunks.py", {"validate_snapshot"}),
        (
            "src/lab_generate_skill/reddit_native_read_runtime.py",
            {"validate_complete_snapshot"},
        ),
        (
            "src/lab_generate_skill/reddit_explicit_submission_runtime.py",
            {"native_author_vote"},
        ),
        (
            "scripts/native_media/reddit_media_state.py",
            {"validate_native_image", "native_media_integrity", "mutation_integrity"},
        ),
    ]:
        source = (ROOT / "codebase" / path).read_bytes()
        if hashlib.sha256(source).hexdigest() != capsule["members"][path]["sha256"]:
            raise ValueError("Original selected media oracle source changed")
        nodes = [
            n
            for n in ast.parse(source).body
            if isinstance(n, ast.FunctionDef) and n.name in names
        ]
        if {n.name for n in nodes} != names:
            raise ValueError("Exact pure original guard functions required")
        exec(
            compile(
                ast.Module(body=list[ast.stmt](nodes), type_ignores=[]),
                str(ROOT / "codebase" / path),
                "exec",
            ),
            namespace,
        )
    assets = [
        dict(sha256=p.sha256, bytes=p.bytes, dimensions=list(p.dimensions))
        for p in PHOTOS
    ]

    def original(initial: dict[str, Any], terminal: dict[str, Any]) -> bool:
        result = namespace["mutation_integrity"](initial, terminal, assets)
        if type(result) is not bool:
            raise ValueError("Original media oracle returned invalid type")
        return result

    return original


def goal_oracle(native_contract_ref: EvidenceRef) -> Callable[..., dict[str, Any]]:
    """Load only two pure original functions; caller separately validates input."""
    from urllib.parse import urlsplit

    raw = (ROOT / "runtime/capsule.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != CAPSULE_SHA:
        raise ValueError("Original selected capsule changed")
    capsule = json.loads(raw)
    pins = {
        "9519ac9ca77e62d2e416a79cb55c4ddaae31cdf55da70dcff7e2b79493c67861": "292ad3eb62765c7e6d93",
        "4306fa4c04813e233ab7265032b6bbd357717a7b9fe8f05c0f0bc13d3295e10a": "dbab57fbe44ffe3192ec",
    }
    if not isinstance(native_contract_ref, EvidenceRef):
        raise TypeError("Explicit original native contract reference required")
    if (
        native_contract_ref.sha256 not in pins
        or native_contract_ref.content_schema != "reddit-native-contract/1"
        or native_contract_ref.media_type != "application/json"
        or native_contract_ref.visibility != "private"
    ):
        raise ValueError("Exact selected original contract reference required")
    selected_source = pins[native_contract_ref.sha256]
    expected_path = ROOT / "bound/bindings/contracts" / (selected_source + ".json")
    expected_raw = expected_path.read_bytes()
    if (
        hashlib.sha256(expected_raw).hexdigest() != native_contract_ref.sha256
        or len(expected_raw) != native_contract_ref.size_bytes
    ):
        raise ValueError("Pinned original contract bytes changed")
    expected_contract = json.loads(expected_raw)

    def enabled(contract: dict[str, Any]) -> None:
        # No old mutable runtime or dispatch is imported. The test supplies the
        # exact fixed contract, already checked by the current input loader.
        if contract != expected_contract:
            raise ValueError("Exact selected original contract required")

    namespace: dict[str, Any] = {
        "urlsplit": urlsplit,
        "enabled": enabled,
        "VERSION": "original-goal-oracle",
    }
    for path, name in (
        ("src/lab_generate_skill/site_navigation_rules.py", "valid_initial_page"),
        ("scripts/native_media/reddit_media_protocol.py", "evaluate"),
    ):
        source = (ROOT / "codebase" / path).read_bytes()
        if hashlib.sha256(source).hexdigest() != capsule["members"][path]["sha256"]:
            raise ValueError("Original selected goal source changed")
        nodes = [
            n
            for n in ast.parse(source).body
            if isinstance(n, ast.FunctionDef) and n.name == name
        ]
        if len(nodes) != 1:
            raise ValueError("Exact original pure goal function required")
        exec(
            compile(
                ast.Module(body=list[ast.stmt](nodes), type_ignores=[]), path, "exec"
            ),
            namespace,
        )

    def original(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = namespace["evaluate"](*args, **kwargs)
        if not isinstance(result, dict):
            raise ValueError("Original goal result invalid")
        return result

    return original

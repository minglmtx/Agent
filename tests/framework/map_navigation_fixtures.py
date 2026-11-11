"""Two exact train fixtures; no website/model/source permission or action script."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any
from lab_generate_skill.bootstrap.map_navigation import load_navigation_inputs
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.map.tasks.navigation_spec import (
    NavigationInputs,
    NavigationSourceBinding,
)

SOURCES = ("0189de83adbd18ca5109", "058c211ed6572633b8e3")
ORIGIN = "http://127.0.0.1:12001"
ROOT = Path(__file__).with_name("fixtures")


def reference(raw: bytes) -> EvidenceRef:
    return EvidenceRef(
        uri="unit:original-map-navigation",
        sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        media_type="application/json",
        content_schema="map-native-contract/1",
        visibility="private",
        producer="unit-original-map",
    )


@dataclass(frozen=True)
class NavigationCase:
    raw: bytes
    native: dict[str, Any]
    binding: NavigationSourceBinding
    public: PublicTask

    def load(self) -> NavigationInputs:
        return load_navigation_inputs(
            self.raw, reference(self.raw), self.public, binding=self.binding
        )


def navigation_case(source: str = SOURCES[0]) -> NavigationCase:
    # The current complete42 retains original pinned files, rather than copies
    # under this old two/eight-member fixture directory.
    if not (ROOT / ("map-navigation-" + source + ".json")).is_file():
        from map_navigation_next_group_fixtures import next_case

        return next_case(source)
    raw = (ROOT / ("map-navigation-" + source + ".json")).read_bytes()
    native = json.loads(raw)
    binding = NavigationSourceBinding.model_validate_json(
        (ROOT / ("map-navigation-binding-" + source + ".json")).read_bytes()
    )
    public = PublicTask(
        identity=TaskIdentity(
            source_task_id=source,
            task_id=binding.active_task_id,
            site="map",
            family="navigation_page_identity",
            split="train",
            contract_version=1,
        ),
        goal=binding.public_goal,
        start_url=ORIGIN + native["start_path"],
        allowed_actions=("click", "send_msg_to_user"),
    )
    return NavigationCase(raw, native, binding, public)


def changed_case(case: NavigationCase, native: dict[str, Any]) -> NavigationCase:
    raw = json.dumps(native, allow_nan=False).encode()
    record = case.binding.model_dump(mode="json")
    record["native_contract"]["sha256"] = reference(raw).sha256
    return NavigationCase(
        raw,
        native,
        NavigationSourceBinding.model_validate_json(json.dumps(record)),
        case.public,
    )

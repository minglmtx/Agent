"""Exact selected complete-group data for the production task source entry.

Selection is not source/dispatch/training permission. No website operation, test
answer or action script is inferred from the private native completion contract.
"""

from dataclasses import dataclass
import hashlib
from urllib.parse import urlsplit
from lab_generate_skill.bootstrap.map_navigation import load_navigation_inputs
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.map_navigation_scope import check_page_navigation_scope
from lab_generate_skill.sites.map.tasks.navigation_spec import (
    NavigationSourceBinding,
    NavigationSpec,
)


@dataclass(frozen=True)
class MapNavigationSourceSelection:
    native: bytes
    binding: NavigationSourceBinding
    public_template: PublicTask

    def __post_init__(self) -> None:
        if type(self.native) is not bytes or not 0 < len(self.native) <= 1024**2:
            raise ValueError("Bounded exact original navigation bytes required")
        if not isinstance(self.public_template, PublicTask) or not isinstance(
            self.binding, NavigationSourceBinding
        ):
            raise TypeError(
                "Validated original navigation public task and binding required"
            )
        self.load(self.reference(), self.public_template)

    def reference(self) -> EvidenceRef:
        return EvidenceRef(
            uri="engineering:original-map-navigation-selection",
            sha256=hashlib.sha256(self.native).hexdigest(),
            size_bytes=len(self.native),
            media_type="application/json",
            content_schema="map-native-contract/1",
            visibility="private",
            producer="original-map-navigation-selection",
        )

    def load(self, reference: EvidenceRef, public: PublicTask) -> NavigationSpec:
        if public.identity != self.public_template.identity:
            raise ValueError("Navigation selection changed original task identity")
        check_page_navigation_scope(public.identity, reference.sha256)
        return load_navigation_inputs(
            self.native, reference, public, binding=self.binding
        ).private_spec

    def public_at(self, endpoint: str, actions: tuple[str, ...] | None) -> PublicTask:
        if type(endpoint) is not str:
            raise TypeError("Original allocated Map endpoint must be text")
        origin = urlsplit(endpoint)
        if (
            origin.scheme != "http"
            or origin.hostname != "127.0.0.1"
            or origin.port is None
            or not 1024 <= origin.port <= 65535
            or endpoint != f"http://127.0.0.1:{origin.port}/"
        ):
            raise ValueError("Original allocated Map root endpoint required")
        private = self.load(self.reference(), self.public_template)
        public = PublicTask.model_validate(
            self.public_template.model_copy(
                update={
                    "start_url": endpoint.rstrip("/") + private.original_start_path,
                    "allowed_actions": (
                        self.public_template.allowed_actions
                        if actions is None
                        else actions
                    ),
                }
            )
        )
        self.load(self.reference(), public)
        return public

"""Explicit selected native/public declaration for the existing engineering entry."""

from dataclasses import dataclass
import hashlib
from lab_generate_skill.bootstrap.reddit_native_image import load_image_inputs
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.reddit_image_start import image_start_path


@dataclass(frozen=True)
class RedditSourceSelection:
    native: bytes
    public_template: PublicTask

    def __post_init__(self) -> None:
        if not isinstance(self.public_template, PublicTask):
            raise TypeError(
                "Selected original public template must be a validated PublicTask"
            )
        if type(self.native) is not bytes or not 0 < len(self.native) <= 1024 * 1024:
            raise ValueError(
                "Selected bounded original native declaration bytes required"
            )
        reference = EvidenceRef(
            uri="engineering:original-reddit-selection",
            sha256=hashlib.sha256(self.native).hexdigest(),
            size_bytes=len(self.native),
            media_type="application/json",
            content_schema="reddit-native-contract/1",
            visibility="private",
            producer="original-reddit-selection",
        )
        load_image_inputs(self.native, reference, self.public_template)

    def public_at(self, endpoint: str, actions: tuple[str, ...] | None) -> PublicTask:
        if type(endpoint) is not str:
            raise TypeError("Allocated Reddit endpoint must be text")
        task = PublicTask.model_validate(
            self.public_template.model_copy(
                update={
                    "start_url": endpoint.rstrip("/")
                    + image_start_path(self.public_template.identity),
                    "allowed_actions": (
                        self.public_template.allowed_actions
                        if actions is None
                        else actions
                    ),
                }
            )
        )
        reference = EvidenceRef(
            uri="engineering:original-reddit-selection",
            sha256=hashlib.sha256(self.native).hexdigest(),
            size_bytes=len(self.native),
            media_type="application/json",
            content_schema="reddit-native-contract/1",
            visibility="private",
            producer="original-reddit-selection",
        )
        load_image_inputs(self.native, reference, task)
        return task

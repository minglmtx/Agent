"""Selected original native image start/account/files, private and not authority."""

from typing import Literal, Self
from urllib.parse import urlsplit
from pydantic import Field, model_validator
from .validation import Contract
from .evidence import EvidenceRef
from .browser_session import BrowserSessionSpec
from .browser_task_files import BrowserTaskFilesPlan
from .task import PublicTask
from .reddit_image_start import image_start_path


class RedditNativeImageInitialization(Contract):
    kind: Literal["reddit_native_image"] = "reddit_native_image"
    endpoint: str = Field(min_length=1, max_length=4096)
    native_account_id: int = Field(ge=1, le=9223372036854775807)
    native_account_username: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    prepared_ref: EvidenceRef
    site_ref: EvidenceRef
    task_files: BrowserTaskFilesPlan

    @model_validator(mode="after")
    def original_inputs(self) -> Self:
        url = urlsplit(self.endpoint)
        if (
            url.scheme != "http"
            or url.hostname != "127.0.0.1"
            or url.port is None
            or not 1024 <= url.port <= 65535
            or self.endpoint != f"http://127.0.0.1:{url.port}/"
        ):
            raise ValueError("Original private Reddit root loopback endpoint required")
        for ref, schema in (
            (self.prepared_ref, "prepared-task/1"),
            (self.site_ref, "site-resource-started/1"),
        ):
            if (ref.visibility, ref.media_type, ref.content_schema) != (
                "private",
                "application/json",
                schema,
            ):
                raise ValueError(
                    "Private original Reddit preparation/site evidence required"
                )
        task = self.task_files.scope.task
        if (task.site, task.family, task.contract_version, task.split) != (
            "reddit",
            "native_image_submission",
            1,
            "train",
        ):
            raise ValueError(
                "Reddit native-image files require the selected original task family"
            )
        return self

    def check(self, spec: BrowserSessionSpec) -> None:
        self.check_task(spec.task)
        self.task_files.check(spec)

    def check_task(self, task: PublicTask) -> None:
        if (
            task.identity.site,
            task.identity.family,
            task.identity.contract_version,
            task.identity.split,
        ) != ("reddit", "native_image_submission", 1, "train"):
            raise ValueError("Unsupported Reddit native-image browser task family")
        if task.start_url != self.endpoint.rstrip("/") + image_start_path(
            task.identity
        ):
            raise ValueError(
                "Reddit task must retain its original selected public start"
            )

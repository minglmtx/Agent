"""Selected root navigation and private measured account pin, never permission."""

from typing import Any, Literal, Self
from urllib.parse import urlsplit
from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)
from .validation import Contract
from .evidence import EvidenceRef
from .browser_session import BrowserSessionSpec
from .task import PublicTask


def check_original_gitlab_inputs(
    endpoint: str, prepared_ref: EvidenceRef, site_ref: EvidenceRef
) -> None:
    url = urlsplit(endpoint)
    if (
        url.scheme != "http"
        or url.hostname != "127.0.0.1"
        or url.port is None
        or not 1024 <= url.port <= 65535
        or endpoint != f"http://127.0.0.1:{url.port}/"
    ):
        raise ValueError("Original private GitLab root loopback endpoint required")
    for ref, schema in (
        (prepared_ref, "prepared-task/1"),
        (site_ref, "site-resource-started/1"),
    ):
        if (ref.visibility, ref.media_type, ref.content_schema) != (
            "private",
            "application/json",
            schema,
        ):
            raise ValueError(
                "Private original GitLab preparation/site evidence required"
            )


class GitlabSshKeyInitialization(Contract):
    kind: Literal["gitlab_profile_ssh_key"] = "gitlab_profile_ssh_key"
    endpoint: str = Field(min_length=1, max_length=4096)
    native_account_id: int = Field(ge=1, le=9223372036854775807)
    prepared_ref: EvidenceRef
    site_ref: EvidenceRef

    @model_validator(mode="after")
    def original_private_inputs(self) -> Self:
        check_original_gitlab_inputs(self.endpoint, self.prepared_ref, self.site_ref)
        return self

    def check(self, spec: BrowserSessionSpec) -> None:
        self.check_task(spec.task)

    def check_task(self, task: PublicTask) -> None:
        if (
            task.identity.site,
            task.identity.family,
            task.identity.contract_version,
            task.identity.split,
        ) != ("gitlab", "profile_ssh_key", 1, "train"):
            raise ValueError("Unsupported GitLab SSH-key browser task family")
        if task.start_url != self.endpoint:
            raise ValueError("GitLab task must retain the original public root start")


class GitlabGroupInitialization(Contract):
    kind: Literal["gitlab_group_creation"] = "gitlab_group_creation"
    endpoint: str = Field(min_length=1, max_length=4096)
    native_account_id: int = Field(ge=1, le=9223372036854775807)
    prepared_ref: EvidenceRef
    site_ref: EvidenceRef
    start_path: Literal["/", "/groups/new", "/groups/new#create-group-pane"] = (
        "/groups/new"
    )

    @model_serializer(mode="wrap")
    def original_declarations(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        values: dict[str, Any] = handler(self)
        if "start_path" not in self.model_fields_set:
            values.pop("start_path", None)
        return values

    @model_validator(mode="after")
    def original_private_inputs(self) -> Self:
        check_original_gitlab_inputs(self.endpoint, self.prepared_ref, self.site_ref)
        return self

    def check(self, spec: BrowserSessionSpec) -> None:
        self.check_task(spec.task)

    def check_task(self, task: PublicTask) -> None:
        if (
            task.identity.site,
            task.identity.family,
            task.identity.contract_version,
            task.identity.split,
        ) != ("gitlab", "group_creation", 1, "train"):
            raise ValueError("Unsupported GitLab Group browser task family")
        if task.start_url != self.endpoint + self.start_path.removeprefix("/"):
            raise ValueError(
                "Group task must retain its declared original public start"
            )

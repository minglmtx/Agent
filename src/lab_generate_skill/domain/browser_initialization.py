"""Explicit browser setup selection; private references grant no authority."""

from typing import Annotated, Literal, Self
import re
from urllib.parse import urlsplit
from pydantic import Field, model_validator
from .validation import Contract
from .evidence import EvidenceRef
from .browser_session import BrowserSessionSpec
from .task import PublicTask
from .reddit_browser_initialization import RedditNativeImageInitialization
from .gitlab_browser_initialization import (
    GitlabSshKeyInitialization,
    GitlabGroupInitialization,
)
from .map_browser_initialization import MapNativeInitialization
from .map_navigation_browser_initialization import MapNavigationInitialization
from .admin_navigation_browser_initialization import AdminNavigationInitialization
from .shopping_navigation_browser_initialization import ShoppingCategoryInitialization


class PublicNavigation(Contract):
    kind: Literal["public_navigation"] = "public_navigation"


class AdminProductInitialization(Contract):
    kind: Literal["admin_product"] = "admin_product"
    endpoint: str = Field(min_length=1, max_length=4096)
    prepared_ref: EvidenceRef
    site_ref: EvidenceRef

    @model_validator(mode="after")
    def private_inputs(self) -> Self:
        url = urlsplit(self.endpoint)
        if (
            url.scheme != "http"
            or url.hostname != "127.0.0.1"
            or url.port is None
            or not 1024 <= url.port <= 65535
            or url.username is not None
            or url.password is not None
            or url.path != "/admin"
            or url.query
            or url.fragment
            or self.endpoint != f"http://127.0.0.1:{url.port}/admin"
        ):
            raise ValueError("Original private Admin loopback endpoint required")
        for ref, schema in (
            (self.prepared_ref, "prepared-task/1"),
            (self.site_ref, "site-resource-started/1"),
        ):
            if (ref.visibility, ref.media_type, ref.content_schema) != (
                "private",
                "application/json",
                schema,
            ):
                raise ValueError("Private original preparation/site evidence required")
        return self

    def check(self, spec: BrowserSessionSpec) -> None:
        self.check_task(spec.task)

    def check_task(self, task: PublicTask) -> None:
        expected = urlsplit(self.endpoint)
        actual = urlsplit(task.start_url)
        if (
            task.identity.site,
            task.identity.family,
            task.identity.contract_version,
        ) != ("shopping_admin", "product_description", 1):
            raise ValueError("Unsupported Admin browser task family")
        if (
            (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc)
            or re.fullmatch(
                r"/admin/catalog/product/edit/id/[1-9][0-9]*/store/[0-9]+/", actual.path
            )
            is None
            or actual.query
            or actual.fragment
        ):
            raise ValueError(
                "Public task start must belong to the original Admin instance"
            )


class ShoppingOrderInitialization(Contract):
    kind: Literal["shopping_order_eta"] = "shopping_order_eta"
    endpoint: str = Field(min_length=1, max_length=4096)
    prepared_ref: EvidenceRef
    site_ref: EvidenceRef

    @model_validator(mode="after")
    def private_inputs(self) -> Self:
        url = urlsplit(self.endpoint)
        if (
            url.scheme != "http"
            or url.hostname != "127.0.0.1"
            or url.port is None
            or not 1024 <= url.port <= 65535
            or url.username is not None
            or url.password is not None
            or url.path != "/"
            or url.query
            or url.fragment
            or self.endpoint != f"http://127.0.0.1:{url.port}/"
        ):
            raise ValueError("Original private Shopping loopback endpoint required")
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
                    "Private original Shopping preparation/site evidence required"
                )
        return self

    def check(self, spec: BrowserSessionSpec) -> None:
        self.check_task(spec.task)

    def check_task(self, task: PublicTask) -> None:
        if (
            task.identity.site,
            task.identity.family,
            task.identity.contract_version,
        ) != ("shopping", "recorded_order_eta", 1):
            raise ValueError("Unsupported Shopping browser task family")
        wanted, actual = urlsplit(self.endpoint), urlsplit(task.start_url)
        if (
            (actual.scheme, actual.netloc) != (wanted.scheme, wanted.netloc)
            or actual.path != "/customer/account/"
            or actual.query
            or actual.fragment
        ):
            raise ValueError(
                "Public task start must belong to original Shopping account"
            )


BrowserInitialization = Annotated[
    PublicNavigation
    | AdminProductInitialization
    | AdminNavigationInitialization
    | ShoppingOrderInitialization
    | ShoppingCategoryInitialization
    | GitlabSshKeyInitialization
    | GitlabGroupInitialization
    | RedditNativeImageInitialization
    | MapNativeInitialization
    | MapNavigationInitialization,
    Field(discriminator="kind"),
]

"""Frozen browser worker configuration shared by resource and wire contracts.

This pure declaration grants no permission and performs no path I/O. Actual
installation, immutable assets and resource ownership are verified at launch.
"""

from pathlib import PurePosixPath
from typing import Literal, Self
from pydantic import Field, model_validator
from .validation import Contract
from .browser_session import BrowserSessionSpec
from .release_installation import ReleaseInstallation
from .browser_initialization import (
    BrowserInitialization,
    AdminProductInitialization,
    ShoppingOrderInitialization,
)
from .reddit_browser_initialization import RedditNativeImageInitialization
from .gitlab_browser_initialization import (
    GitlabSshKeyInitialization,
    GitlabGroupInitialization,
)
from .map_browser_inputs import MapBrowserInputs
from .map_browser_initialization import MapNativeInitialization
from .map_navigation_browser_initialization import MapNavigationInitialization
from .admin_navigation_browser_initialization import AdminNavigationInitialization
from .shopping_navigation_browser_initialization import ShoppingCategoryInitialization


class BrowserWorkerConfiguration(Contract):
    schema_version: Literal["browser-worker-configuration/3"] = (
        "browser-worker-configuration/3"
    )
    spec: BrowserSessionSpec
    initialization: BrowserInitialization
    installation: ReleaseInstallation
    playwright_browsers_path: str = Field(min_length=1, max_length=4096)
    library_directories: tuple[str, ...] = Field(max_length=16)
    map_inputs: MapBrowserInputs | None = None

    @model_validator(mode="after")
    def paths(self) -> Self:
        if (self.spec.task.identity.site, self.spec.task.identity.family) == (
            "map",
            "native_route_map_data",
        ):
            if self.map_inputs is None or self.map_inputs.plan.scope != self.spec.scope:
                raise ValueError(
                    "Map browser requires its exact frozen collection scope"
                )
            if self.initialization.kind not in (
                "public_navigation",
                "map_native_overlay",
            ):
                raise ValueError(
                    "Selected Map browser requires original public navigation"
                )
        elif (self.spec.task.identity.site, self.spec.task.identity.family) == (
            "map",
            "navigation_page_identity",
        ):
            if self.map_inputs is not None or not isinstance(
                self.initialization, MapNavigationInitialization
            ):
                raise ValueError(
                    "Navigation requires explicit original initialization without MapData collection"
                )
        elif (self.spec.task.identity.site, self.spec.task.identity.family) == (
            "shopping_admin",
            "page_navigation",
        ):
            if self.map_inputs is not None or not isinstance(
                self.initialization, AdminNavigationInitialization
            ):
                raise ValueError(
                    "Admin navigation requires explicit original authenticated initialization"
                )
        elif (self.spec.task.identity.site, self.spec.task.identity.family) == (
            "shopping",
            "page_navigation",
        ):
            if self.map_inputs is not None or not isinstance(
                self.initialization, ShoppingCategoryInitialization
            ):
                raise ValueError(
                    "Category requires explicit original-start initialization"
                )
        elif self.map_inputs is not None:
            raise ValueError(
                "Map browser collection cannot be attached to another site"
            )
        if isinstance(
            self.initialization,
            (
                AdminProductInitialization,
                AdminNavigationInitialization,
                ShoppingOrderInitialization,
                ShoppingCategoryInitialization,
                GitlabSshKeyInitialization,
                GitlabGroupInitialization,
                RedditNativeImageInitialization,
                MapNativeInitialization,
                MapNavigationInitialization,
            ),
        ):
            self.initialization.check(self.spec)
        paths = (
            self.playwright_browsers_path,
            *self.library_directories,
            self.spec.chromium_executable,
        )
        for value in paths:
            path = PurePosixPath(value)
            if (
                not path.is_absolute()
                or str(path) != value
                or ".." in path.parts
                or any(c in value for c in ("\0", ":", "\\"))
            ):
                raise ValueError("Worker assets require canonical absolute paths")
        if len(set(self.library_directories)) != len(self.library_directories):
            raise ValueError("Duplicate browser library directories")
        if not PurePosixPath(self.spec.chromium_executable).is_relative_to(
            self.playwright_browsers_path
        ):
            raise ValueError(
                "Frozen Chromium must belong to its declared browser cache"
            )
        return self

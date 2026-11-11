"""Explicit native unit boundary shared by original MapData and Navigation tests."""

from collections.abc import Callable
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.site_capture import SiteCaptureRequest
from map_registered_worker_fixtures import RegisteredMapCase
from map_qualified_source_native import MapQualifiedSource
from map_site_engineering_authority import MapEngineeringAuthority


def source_native_boundary(
    c: RegisteredMapCase,
    source: MapQualifiedSource,
    patch: pytest.MonkeyPatch,
    captured: list[str],
    before_capture: Callable[[SiteCaptureRequest], None] | None = None,
) -> None:
    source_native_ports(c, source, patch, captured, before_capture)
    authority = MapEngineeringAuthority(
        c.resource, Path(c.configuration.files.node_root).parent
    )
    authority.before_native = True
    authority.task_input = source.native.private_input_json()
    c.resource.authority = authority


def source_native_ports(
    c: RegisteredMapCase,
    source: MapQualifiedSource,
    patch: pytest.MonkeyPatch,
    captured: list[str],
    before_capture: Callable[[SiteCaptureRequest], None] | None = None,
) -> None:
    original = source.site.tasks.execute_task

    def execute(*args: Any, **kwargs: Any) -> Any:
        c.observer = "worker"
        try:
            return original(*args, **kwargs)
        finally:
            c.observer = "controller"

    patch.setattr(source.site.tasks, "execute_task", execute)
    old_capture = source.site.capture.capture_task

    def site_capture(*args: Any, **kwargs: Any) -> Any:
        c.observer = "worker"
        captured.append(args[0].collector_id)
        if before_capture is not None:
            before_capture(args[0])

        class ParentAuthority:
            def verify_capture(self, *values: Any) -> None:
                c.observer = "controller"
                try:
                    args[2].verify_capture(*values)
                finally:
                    c.observer = "worker"

        try:
            return old_capture(args[0], args[1], ParentAuthority(), **kwargs)
        finally:
            c.observer = "controller"

    patch.setattr(source.site.capture, "capture_task", site_capture)
    old_resume = source.site.resume.resume_frontend

    def resume(*args: Any, **kwargs: Any) -> Any:
        c.observer = "worker"
        try:
            return old_resume(*args, **kwargs)
        finally:
            c.observer = "controller"

    patch.setattr(source.site.resume, "resume_frontend", resume)

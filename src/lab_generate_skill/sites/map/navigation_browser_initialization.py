"""Only original start navigation and passive readiness; no second Observation."""

import json
import os
import threading
from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.lifecycle import Clock, OperationControl
from .native_view_wait import NativeViewWait
from .navigation_initial_rules import (
    same_start_document,
    navigation_readiness_arguments,
)
from .navigation_page_capture import navigation_page
from .navigation_initial_evidence import NavigationInitialReadiness


class MapNavigationBrowserInitializer:
    def __init__(self, config: MapNavigationInitialization, clock: Clock) -> None:
        self.config = MapNavigationInitialization.model_validate(config)
        self.owner = os.getpid(), threading.get_ident()
        self.waiter = NativeViewWait(clock)
        self.attempted = False
        self.page: Any = None
        self.task: PublicTask | None = None
        self.fact: NavigationInitialReadiness | None = None
        self.error: BaseException | None = None

    def check_owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original browser thread owns navigation setup")

    def setup(self, page: Any, task: PublicTask, control: OperationControl) -> None:
        self.check_owner()
        if self.attempted:
            raise InvalidTransition("Navigation initialization already attempted")
        control.checkpoint()
        task = PublicTask.model_validate(task)
        self.config.check_task(task)
        mapped = urlsplit(task.start_url).path in ("/", "/search", "/directions")
        if mapped:
            navigation_readiness_arguments(task)
        elif urlsplit(task.start_url).path not in ("/communities", "/traces"):
            raise ValueError(
                "Only selected original map/search/directions/Communities/traces start supported"
            )
        if page.url != "about:blank":
            raise OwnershipConflict("Navigation setup requires original first document")
        self.attempted, self.page, self.task = True, page, task
        try:
            page.goto(task.start_url, timeout=min(10000, control.checkpoint() * 1000))
            if not same_start_document(task, page.url):
                raise OwnershipConflict("Original navigation initial document changed")
            if mapped:
                self.waiter.wait_navigation(page, task, control)
            else:
                page.wait_for_function(
                    "() => document.readyState === 'complete'",
                    timeout=min(10000, control.checkpoint() * 1000),
                )
            sampled = navigation_page(page, control)
            health = sampled.health
            if (
                sampled.document_state != "complete"
                or health.http_status is None
                or not 200 <= health.http_status < 300
                or health.error_page
                or health.login_page
                or not same_start_document(task, health.url)
            ):
                raise ValueError(
                    "Original native initial document not confirmed healthy"
                )
            if mapped and (
                type(self.waiter.last_view) is not dict
                or self.waiter.last_view.get("map_visible") is not True
            ):
                raise ValueError("Original initial map is not visible")
            self.fact = NavigationInitialReadiness(
                initialization=self.config,
                start_url=task.start_url,
                page=sampled,
                native_signal_json=(
                    None
                    if not mapped
                    else json.dumps(
                        self.waiter.last_signal_raw, ensure_ascii=False, allow_nan=False
                    )
                ),
                native_view_json=(
                    None
                    if not mapped
                    else json.dumps(
                        self.waiter.last_view, ensure_ascii=False, allow_nan=False
                    )
                ),
                stable_seconds=self.waiter.settled_seconds,
            )
            control.checkpoint()
        except BaseException as error:
            self.error = error
            raise

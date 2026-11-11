"""One original directions navigation, passive readiness and complete private fact."""

import hashlib
import json
import os
import threading
import traceback
from typing import Any
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    EvidenceIntegrityError,
)
from lab_generate_skill.ports.lifecycle import Clock, OperationControl
from lab_generate_skill.ports.map_private_artifact import MapArtifactSink
from .native_view_rules import selected_public, original_document
from .native_view_wait import NativeViewWait


class MapNativeBrowserInitializer:
    def __init__(
        self, config: MapNativeInitialization, clock: Clock, evidence: MapArtifactSink
    ) -> None:
        self.config = MapNativeInitialization.model_validate(config)
        self.waiter = NativeViewWait(clock)
        self.evidence = evidence
        self.owner = os.getpid(), threading.get_ident()
        self.attempted = False
        self.last_fact: bytes | None = None
        self.reference: ReleaseFile | None = None
        self.error: BaseException | None = None
        self.failure_fact: bytes | None = None
        self.failure_ref: ReleaseFile | None = None

    def setup(self, page: Any, task: PublicTask, control: OperationControl) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original browser thread owns Map initialization")
        if self.attempted:
            raise InvalidTransition("Original Map initialization already attempted")
        control.checkpoint()
        task = PublicTask.model_validate(task)
        self.config.check_task(task)
        selected_public(task)
        if page.url != "about:blank":
            raise OwnershipConflict(
                "Map initialization requires original first navigation"
            )
        self.attempted = True
        try:
            self._navigate(page, task, control)
        except BaseException as error:
            self.error = error
            try:
                self.failure_fact = json.dumps(
                    {
                        "schema_version": "map-native-initial-readiness-failure/1",
                        "initialization": self.config.model_dump(mode="json"),
                        "last_native_readiness": self.waiter.last_signal_raw,
                        "last_native_view": self.waiter.last_view,
                        "error": "".join(traceback.format_exception(error)),
                        "new_observation_created": False,
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode()
                expected = ReleaseFile(
                    path="map-initial-readiness-failure.json",
                    sha256=hashlib.sha256(self.failure_fact).hexdigest(),
                    size_bytes=len(self.failure_fact),
                    executable=False,
                )
                self.failure_ref = self.evidence.retain(
                    expected.path, self.failure_fact, control
                )
                if self.failure_ref != expected:
                    raise EvidenceIntegrityError("Map failure evidence receipt changed")
            except BaseException as retention:
                raise BaseExceptionGroup(
                    "Original Map initialization and failure retention failed",
                    [error, retention],
                ) from None
            raise

    def _navigate(self, page: Any, task: PublicTask, control: OperationControl) -> None:
        page.goto(task.start_url, timeout=min(10000, control.checkpoint() * 1000))
        if not original_document(task, page.url):
            raise OwnershipConflict("Original Map first document changed")
        self.waiter.wait(page, control)
        self.last_fact = json.dumps(
            {
                "schema_version": "map-native-initial-readiness/1",
                "initialization": self.config.model_dump(mode="json"),
                "public_task": task.model_dump(mode="json"),
                "native_readiness": self.waiter.last_signal,
                "native_view": self.waiter.last_view,
                "stable_seconds": self.waiter.settled_seconds,
                "new_observation_created": False,
                "task_success_or_admission_claim": False,
            },
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        expected = ReleaseFile(
            path="map-initial-readiness.json",
            sha256=hashlib.sha256(self.last_fact).hexdigest(),
            size_bytes=len(self.last_fact),
            executable=False,
        )
        self.reference = self.evidence.retain(expected.path, self.last_fact, control)
        if self.reference != expected:
            raise EvidenceIntegrityError("Map original readiness file receipt changed")
        control.checkpoint()

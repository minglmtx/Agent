"""Selected process-to-capture lifecycle, preserving the existing unique readout.

Complete files are privately retained. A successful terminal capture settles
only existing requests, stops original transport, then seals once. Partial or
unknown failures keep their original files and never replay native collection.
No task verdict, initial-state admission, extra navigation or observation.
"""

import hashlib
import os
import threading
from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.browser_session import BrowserSessionSpec, BrowserReadout
from lab_generate_skill.domain.map_browser_inputs import MapBrowserInputs
from lab_generate_skill.domain.map_browser_collection import MapBrowserPublication
from lab_generate_skill.domain.errors import (
    InvalidTransition,
    OwnershipConflict,
    EvidenceIntegrityError,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.map_browser_collection import (
    MapBrowserFiles,
    MapBrowserSources,
    MapBrowserLifetime,
)
from .native_relay import NativeMapRelay
from .native_route_collector import MapNativeRequestCollector
from .native_process_collector import MapNativeProcessCollector
from .native_served_capture import NativeServedCapture
from .native_notes_capture import NativeNotesCapture


class MapBrowserCollection:
    def __init__(
        self,
        spec: BrowserSessionSpec,
        inputs: MapBrowserInputs,
        sources: MapBrowserSources,
        files: MapBrowserFiles,
        lifetime: MapBrowserLifetime,
    ) -> None:
        self.spec = BrowserSessionSpec.model_validate(spec)
        self.inputs = MapBrowserInputs.model_validate(inputs)
        if self.spec.scope != self.inputs.plan.scope:
            raise OwnershipConflict("Map collection changed original browser scope")
        self.sources, self.files, self.lifetime = sources, files, lifetime
        self.owner = os.getpid(), threading.get_ident()
        self.state = "new"
        self.page: Any = None
        self.native: MapNativeProcessCollector | None = None
        self.native_close_attempted = False
        self.cleanup_errors: list[BaseException] = []
        self.publication: MapBrowserPublication | None = None

    def _owner(self) -> None:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original browser thread owns collection lifecycle")

    def _active(self) -> MapNativeProcessCollector:
        self._owner()
        if self.state != "active" or self.native is None:
            raise InvalidTransition("Original Map collection is not active")
        return self.native

    def attach(
        self, page: Any, spec: BrowserSessionSpec, control: OperationControl
    ) -> None:
        self._owner()
        if self.state != "new":
            raise InvalidTransition("Map collection attaches only once")
        if spec != self.spec or page.url != "about:blank":
            raise OwnershipConflict(
                "Map collection must precede original first navigation"
            )
        bound = self.lifetime.intersect(control)
        bound.checkpoint()
        self.state, self.page = "attaching", page
        try:
            originals = self.sources.read(bound)
            url = urlsplit(self.spec.task.start_url)
            origin = f"{url.scheme}://{url.netloc}"
            plan, collection = self.inputs.plan, self.inputs.collection
            served = NativeServedCapture(
                plan,
                self.files,
                self.lifetime,
                origin,
                originals,
                collection.tile_origin,
            )
            relay = NativeMapRelay(
                origin, self.files, self.lifetime, max_requests=collection.max_requests
            )
            self.native = MapNativeProcessCollector(
                MapNativeRequestCollector(plan, relay),
                served=served,
                notes=NativeNotesCapture(plan, self.files, self.lifetime, origin),
            )
            self.files.initialize(bound)
            self.files.retain(
                "map-collection-intent.json",
                self.inputs.model_dump_json().encode(),
                bound,
            )
            self.native.attach(page, spec, bound)
            self.state = "active"
        except BaseException:
            self.state = "failed"
            raise

    def before_action(self, control: OperationControl) -> None:
        self._active().before_action(self.lifetime.intersect(control))

    def observe(
        self, page: Any, readout: BrowserReadout, control: OperationControl
    ) -> None:
        native = self._active()
        if page is not self.page:
            raise OwnershipConflict("Map collection changed original page")
        try:
            native.observe(page, readout, self.lifetime.intersect(control))
        except BaseException:
            self.state = "failed"
            raise

    def collect(
        self,
        page: Any,
        collector_id: str,
        collector_version: str,
        control: OperationControl,
    ) -> str:
        native = self._active()
        if (collector_id, collector_version) != (
            "map-native-process",
            "1",
        ) or page is not self.page:
            raise OwnershipConflict(
                "Only original selected terminal Map capture is supported"
            )
        readout = native.requests.last_readout
        if readout is None:
            raise InvalidTransition("Terminal capture needs an original browser return")
        bound = self.lifetime.intersect(control)
        bound.checkpoint()
        self.state = "capturing"
        try:
            native.finish(bound)
            terminal = self.files.retain(
                "map-terminal-readout.json", readout.model_dump_json().encode(), bound
            )
            self._close_native(bound)
            if not native.requests.relay.physical_closed:
                raise EvidenceIntegrityError(
                    "Original Map transport is not physically stopped"
                )
            handle = self.files.seal(bound)
            self.publication = MapBrowserPublication(
                plan=self.inputs.plan,
                collection_sha256=self.inputs.collection.digest,
                handle=handle,
                terminal_readout=terminal,
                observation_sha256=hashlib.sha256(
                    readout.observation.model_dump_json().encode()
                ).hexdigest(),
                sequence=readout.observation.sequence,
            )
            self.files.stop_new_io()
            self.state = "published"
            bound.checkpoint()
            return self.publication.model_dump_json()
        except BaseException:
            self.state = "failed"
            raise

    def _close_native(self, control: OperationControl) -> None:
        if not self.native_close_attempted and self.native is not None:
            self.native_close_attempted = True
            try:
                self.native.close(control)
            except BaseException as error:
                self.cleanup_errors.append(error)
        if self.cleanup_errors:
            raise BaseExceptionGroup(
                "Original Map collection close incomplete", self.cleanup_errors
            )

    def close(self, control: OperationControl) -> None:
        self._owner()
        if self.state == "closed":
            return
        try:
            # Cleanup keeps its independent caller deadline; no new native work,
            # no renewed collection deadline and no implicit finish/seal retry.
            self._close_native(control)
        finally:
            self.files.stop_new_io()
            self.state = "closed" if not self.cleanup_errors else "failed"

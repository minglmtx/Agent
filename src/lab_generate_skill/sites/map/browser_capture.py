"""Export already retained initial facts once; keep terminal collection active."""

import hashlib
import os
import threading
from typing import Any
from lab_generate_skill.domain.map_initial_capture import MapInitialCapture
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl
from .browser_collection import MapBrowserCollection
from .browser_initialization import MapNativeBrowserInitializer
from .initial_readiness_rules import original_readiness
from .page_capture import MapPageHealthCapture


class MapBrowserCapture:
    def __init__(
        self, process: MapBrowserCollection, initialization: MapNativeBrowserInitializer
    ) -> None:
        if (
            initialization.evidence is not process.files
            or initialization.owner != process.owner
        ):
            raise OwnershipConflict(
                "Map initial capture requires same original files/thread"
            )
        self.process, self.initialization = process, initialization
        self.health = MapPageHealthCapture(process)
        self.attempted = False
        self.initial: MapInitialCapture | None = None

    def collect(
        self,
        page: Any,
        collector_id: str,
        collector_version: str,
        control: OperationControl,
    ) -> str:
        if collector_id == "map-page-health":
            return self.health.collect(page, collector_version, control)
        if collector_id == "map-native-process":
            return self.process.collect(page, collector_id, collector_version, control)
        p, i = self.process, self.initialization
        if (
            (collector_id, collector_version) != ("map-initial-readiness", "1")
            or page is not p.page
            or p.owner != (os.getpid(), threading.get_ident())
        ):
            raise OwnershipConflict(
                "Only original selected Map initial/terminal capture supported"
            )
        if (
            self.attempted
            or p.state != "active"
            or p.native is None
            or i.reference is None
            or i.last_fact is None
            or i.error is not None
        ):
            raise InvalidTransition(
                "Original Map readiness capture unavailable or already attempted"
            )
        readout = p.native.requests.last_readout
        if (
            readout is None
            or readout.schema_version != "browser-initial-return/1"
            or readout.observation.sequence != 0
            or readout.action is not None
            or (
                readout.scope != p.spec.scope
                or readout.operation != p.inputs.collection.operation
                or readout.terminated
                or readout.truncated
                or readout.protocol_terminal
            )
        ):
            raise InvalidTransition(
                "Map initial capture requires original unique first return"
            )
        bound = p.lifetime.intersect(control)
        bound.checkpoint()
        self.attempted = True
        original_readiness(i.last_fact, i.config, p.spec.task)
        result = MapInitialCapture(
            plan=p.inputs.plan,
            collection_sha256=p.inputs.collection.digest,
            readout_sha256=hashlib.sha256(
                readout.model_dump_json().encode()
            ).hexdigest(),
            observation_sha256=hashlib.sha256(
                readout.observation.model_dump_json().encode()
            ).hexdigest(),
            readiness_file=i.reference,
            readiness_json=i.last_fact.decode("utf-8"),
        )
        raw = result.model_dump_json()
        if len(raw.encode()) > 262144:
            raise ValueError(
                "Complete initial readiness exceeds original capture reply bound"
            )
        self.initial = result
        bound.checkpoint()
        return raw

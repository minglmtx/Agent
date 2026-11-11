"""Map's selected Rails replacement, under its original service/resource owner."""

from typing import Protocol
from lab_generate_skill.domain.map_frontend_lifecycle import MapFrontendStopped
from lab_generate_skill.domain.map_frontend_lifecycle import MapFrontendCleared
from lab_generate_skill.domain.map_services import MapServiceSpec
from .native_services import NativeServices
from .lifecycle import OperationControl


class MapFrontendServices(NativeServices, Protocol):
    def retire_frontend(self, control: OperationControl) -> MapFrontendStopped:
        """Stop original Rails once; prove held namespace and master exited.

        Retain original grace timeout if bounded forced namespace stop is needed.
        Caller cancellation/other errors do not authorize replacement. This is
        neither a database snapshot proof nor whole registered resource closure.
        """
        ...

    def replace_frontend(self, control: OperationControl) -> None:
        """After confirmed retirement only, launch exact original Rails argv once.

        Retain every generation/partial effect. New health and namespace pin are
        still required; no implicit frontend preparation, data reset or retry.
        """
        ...


class MapFrontendTransients(Protocol):
    def clear(
        self,
        spec: MapServiceSpec,
        stopped: MapFrontendStopped,
        control: OperationControl,
    ) -> MapFrontendCleared:
        """Once per original stopped generation, clear only selected private transients.

        Preserve same-deployment tmp/cache/assets/sprockets; clear other native
        cache entries and tmp/pids. No public/storage/database/source changes.
        Original registered restore authority and closed browser precede this
        leaf. A supplied data receipt alone grants no permission.
        """
        ...

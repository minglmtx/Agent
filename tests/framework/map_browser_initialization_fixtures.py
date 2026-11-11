"""Selected public input and passive page/clock doubles; no native website claims."""

from datetime import datetime, timezone
import hashlib
from typing import Any
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.release import ReleaseFile
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.overlay_spec import SOURCE, START, GOAL
from lab_generate_skill.sites.map.native_view_scripts import READ, READINESS
from test_core_contracts import reference


def selection(endpoint: str = "http://127.0.0.1:18080/") -> MapNativeInitialization:
    return MapNativeInitialization(
        endpoint=endpoint,
        prepared_ref=reference("private", "prepared-task/1"),
        site_ref=reference("private", "site-resource-started/1"),
    )


def public_task(endpoint: str = "http://127.0.0.1:18080/") -> PublicTask:
    return PublicTask(
        identity=TaskIdentity(
            site="map",
            family="native_route_map_data",
            contract_version=1,
            split="train",
            task_id=SOURCE,
            source_task_id=SOURCE,
        ),
        goal=GOAL,
        start_url=endpoint.rstrip("/") + START,
        allowed_actions=("click", "send_msg_to_user"),
    )


class Clock:
    def __init__(self) -> None:
        self.elapsed = 0.0

    def monotonic(self) -> float:
        return self.elapsed

    def utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def sleep(self, seconds: float) -> None:
        self.elapsed += seconds


class Sink:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.fault = ""

    def retain(self, name: str, data: bytes, control: OperationControl) -> ReleaseFile:
        control.checkpoint()
        assert name not in self.files
        if self.fault == "before":
            raise OSError("original retention failed before commit")
        self.files[name] = data
        if self.fault == "after":
            raise OSError("original retention acknowledgement lost")
        value = ReleaseFile(
            path=name,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            executable=False,
        )
        return (
            value.model_copy(update={"sha256": "f" * 64})
            if self.fault == "wrong"
            else value
        )


class Page:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.url = "about:blank"
        self.calls: list[str] = []
        self.budgets: list[float] = []
        self.arguments: dict[str, Any] | None = None
        self.fault = ""
        self.signal: Any = {
            "geo": "geo:40.77,-73.97?z=14",
            "long": "/#map=14/40.77/-73.97",
            "classes": "leaflet-container",
            "busy": False,
            "loading": False,
            "directionsContent": True,
            "directionsFields": [],
            "ready": True,
        }
        self.view: Any = {
            "map_visible": True,
            "native_geo_uri": "geo:40.77,-73.97?z=14",
            "native_long_link": "/#map=14/40.77/-73.97",
        }
        self.signals = 0

    def goto(self, url: str, *, timeout: float) -> None:
        self.calls.append("goto")
        self.budgets.append(timeout)
        self.url = url
        if self.fault == "redirect":
            self.url = url.replace("/directions", "/search")
        if self.fault == "goto":
            raise OSError("original goto failed")

    def wait_for_function(
        self, script: str, *, arg: dict[str, Any], timeout: float
    ) -> None:
        assert READINESS in script
        self.calls.append("wait-ready")
        self.arguments = arg
        self.budgets.append(timeout)
        if self.fault == "wait":
            raise TimeoutError("original native readiness timed out")

    def evaluate(self, script: str, args: Any = None) -> Any:
        if script == READ:
            self.calls.append("view")
            return self.view
        assert script == READINESS and args == self.arguments
        self.calls.append("signal")
        self.signals += 1
        value = dict(self.signal) if isinstance(self.signal, dict) else self.signal
        if self.fault == "unstable":
            value["classes"] = str(self.signals)
        if self.fault == "pending" and self.clock.elapsed < 0.4:
            value["ready"] = False
        return value

    def wait_for_timeout(self, ms: float) -> None:
        self.clock.elapsed += ms / 1000

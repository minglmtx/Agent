"""Current complete native read + original media collector, without CAS/rights."""

import json
import os
import threading
from typing import Literal, Protocol
from pydantic import JsonValue
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.reddit_native_read_input import BaselineIdsRef
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_input_commands import (
    NativeInputCommands,
    MAX_NATIVE_INPUT_BYTES,
)
from lab_generate_skill.ports.reddit_native_read_input import RedditNativeReadInputs
from .service_contract import RedditServiceSpec
from .service_commands import container
from .native_schema import DatabaseCapture, NativeCapture, NativeMedia
from .image_state import ImageReference
from .tasks.image_spec import NativeImageSpec
from .native_capture_program import CAPTURE


class NativeMediaSource(Protocol):
    def capture(self, control: OperationControl) -> NativeMedia: ...


class DatabaseEnvelope(Contract):
    schema_version: Literal["reddit-native-database-capture/1"] = (
        "reddit-native-database-capture/1"
    )
    task: TaskIdentity
    mode: Literal["reference", "capture"]
    reference: dict[str, JsonValue] | None
    capture: DatabaseCapture


class RedditNativeReader:
    def __init__(
        self,
        services: RedditServiceSpec,
        commands: NativeInputCommands,
        inputs: RedditNativeReadInputs,
        media: NativeMediaSource,
    ) -> None:
        self.services = RedditServiceSpec.model_validate_json(
            services.model_dump_json()
        )
        self.commands, self.inputs, self.media = commands, inputs, media
        self.owner = os.getpid(), threading.get_ident()
        self.last_database: DatabaseEnvelope | None = None
        self.last_result: ImageReference | NativeCapture | None = None

    def _database(
        self,
        spec: NativeImageSpec,
        username: str,
        baseline: BaselineIdsRef | None,
        control: OperationControl,
    ) -> DatabaseEnvelope:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Native reader belongs to original worker/thread")
        spec = NativeImageSpec.model_validate_json(spec.model_dump_json())
        if type(username) is not str or not username or len(username) > 255:
            raise ValueError("Original native benchmark username required")
        if baseline is not None:
            baseline = BaselineIdsRef.model_validate_json(baseline.model_dump_json())
            if baseline.task != spec.task:
                raise OwnershipConflict("Native read input changed original task")
        data = dict(
            mode="capture" if baseline else "reference",
            task=spec.task.model_dump(mode="json"),
            username=username,
            forum=spec.parameters.forum,
            baseline=baseline.model_dump(mode="json") if baseline else None,
        )
        raw = json.dumps(
            data, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
        if not 0 < len(raw) <= MAX_NATIVE_INPUT_BYTES:
            raise ValueError("Native read selector exceeds original stdin byte bound")
        control.checkpoint()
        if baseline is not None:
            self.inputs.verify(baseline, control)
        self.last_database = None
        self.last_result = None
        argv = container(self.services, native_input=baseline is not None) + (
            "/usr/local/bin/php",
            "-r",
            CAPTURE,
            str(self.services.ports.database),
        )
        returned = self.commands.run_input(argv, raw, control)
        if type(returned) is not bytes or not 0 < len(returned) <= 64 * 1024**2:
            raise EvidenceIntegrityError("Complete native read result byte bound")
        result = DatabaseEnvelope.model_validate_json(returned)
        if (
            result.task != spec.task
            or result.mode != data["mode"]
            or (result.reference is None) != (baseline is not None)
        ):
            raise EvidenceIntegrityError(
                "Native database result changed original task or read phase"
            )
        self.last_database = result
        return result

    def reference(
        self, spec: NativeImageSpec, username: str, control: OperationControl
    ) -> ImageReference:
        database = self._database(spec, username, None, control)
        assert database.reference is not None
        fields: dict[str, object] = dict(database.reference)
        capture = database.capture.model_dump(mode="json")
        capture["native_media"] = self.media.capture(control).model_dump(mode="json")
        fields["capture"] = capture
        result = ImageReference.model_validate_json(json.dumps(fields))
        if (
            result.account.username != username
            or result.target_forum.name != spec.parameters.forum
        ):
            raise EvidenceIntegrityError(
                "Original native account/requested forum differs"
            )
        self.last_result = result
        control.checkpoint()
        return result

    def capture(
        self,
        spec: NativeImageSpec,
        username: str,
        baseline: BaselineIdsRef,
        control: OperationControl,
    ) -> NativeCapture:
        database = self._database(spec, username, baseline, control)
        fields = database.capture.model_dump(mode="json")
        fields["native_media"] = self.media.capture(control).model_dump(mode="json")
        result = NativeCapture.model_validate_json(json.dumps(fields))
        self.last_result = result
        control.checkpoint()
        return result

"""Shared process-local model ownership, immutable load and RNG exclusion."""

import os
import threading
from contextlib import contextmanager
from collections.abc import Callable, Iterator
from importlib.metadata import version
from typing import Generic, Protocol, TypeVar
from lab_generate_skill.adapters.releases.files import verify_artifact
from lab_generate_skill.domain.causal_model import (
    ModelPackage,
    validate_causal_artifact,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.release import ReleaseArtifact
from lab_generate_skill.ports.lifecycle import OperationControl


class ClosableSession(Protocol):
    def close(self) -> None: ...


Session = TypeVar("Session", bound=ClosableSession)
_ENGINE_LOCK = threading.Lock()


class ResidentState(Generic[Session]):
    def __init__(
        self,
        artifact: ReleaseArtifact,
        packages: tuple[ModelPackage, ...],
        load: Callable[[], Session],
    ) -> None:
        self._artifact = validate_causal_artifact(artifact)
        self._packages, self._load_session = packages, load
        self._session: Session | None = None
        self._closed = False
        self._pid = os.getpid()

    @property
    def artifact(self) -> ReleaseArtifact:
        return self._artifact

    @contextmanager
    def _held(
        self, control: OperationControl, *, allow_closed: bool = False
    ) -> Iterator[None]:
        if os.getpid() != self._pid:
            raise OwnershipConflict("Model engine cannot cross process boundaries")
        control.checkpoint()
        while not _ENGINE_LOCK.acquire(blocking=False):
            control.wait(0.02)
        try:
            control.checkpoint()
            if self._closed and not allow_closed:
                raise OwnershipConflict("Model engine is closed; no automatic reload")
            yield
        finally:
            _ENGINE_LOCK.release()

    def _close(self) -> None:
        self._closed = True
        session, self._session = self._session, None
        if session is not None:
            session.close()

    def close(self, control: OperationControl) -> None:
        if os.getpid() != self._pid:
            raise OwnershipConflict("Model engine cannot cross process boundaries")
        with self._held(control, allow_closed=True):
            if not self._closed:
                self._close()

    def _failed(self, primary: BaseException) -> None:
        try:
            self._close()
        except BaseException as cleanup:
            raise BaseExceptionGroup(
                "Model operation and release failed", [primary, cleanup]
            ) from None

    def _load(self, control: OperationControl) -> Session:
        if self._session is None:
            try:
                verify_artifact(self.artifact, control)
                for pin in self._packages:
                    control.checkpoint()
                    if version(pin.name) != pin.version:
                        raise EvidenceIntegrityError(
                            "Model package version changed: " + pin.name
                        )
                self._session = self._load_session()
                control.checkpoint()
            except BaseException as error:
                self._failed(error)
                raise
        return self._session

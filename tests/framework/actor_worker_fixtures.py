"""In-memory wire channel around the real service and a deliberate unit engine."""

from pathlib import Path
from lab_generate_skill.domain.process_guard import ProcessOwnerGuard
from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.adapters.models.actor_service import ActorService
from lab_generate_skill.adapters.models.actor_count_protocol import (
    decode_worker_command,
)
from lab_generate_skill.adapters.models.actor_worker_client import (
    SupervisedActorEngine,
)
from lab_generate_skill.adapters.processes.capture import (
    CommandCapture,
    ProcessTermination,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from actor_engine_fixtures import setup, Loader
from actor_installation_fixtures import unit_declaration, unit_verifier
from lab_generate_skill.adapters.models.transformers_actor import (
    ResidentActorEngine,
)
from lab_generate_skill.domain.actor_prompt import ActorPrompt
from lab_generate_skill.domain.actor_engine import LocalActorParameters


def unit_guard(
    controller: ProcessIdentity, control: OperationControl
) -> ProcessOwnerGuard:
    """Synthetic identities only; no OS supervision or production permission."""
    control.checkpoint()
    return ProcessOwnerGuard(
        controller=controller,
        supervisor=controller.model_copy(
            update={"process_id": controller.process_id + 10000000}
        ),
        worker=controller.model_copy(
            update={"process_id": controller.process_id + 10000001}
        ),
    )


class UnitChannel:
    def __init__(self, service: ActorService) -> None:
        self.service = service
        self.sent: list[bytes] = []
        self.aborts = 0
        self.finishes = 0
        self.failure: BaseException | None = None
        self.cleanup_failure: BaseException | None = None
        self.broken_reply: bytes | None = None
        self.capture = CommandCapture(("/unit-worker",), None, b"", b"", False)

    def exchange(self, payload: bytes, control: OperationControl) -> bytes:
        control.checkpoint()
        self.sent.append(payload)
        if self.failure is not None:
            raise self.failure
        result = (
            self.service.handle(decode_worker_command(payload))
            .model_dump_json()
            .encode()
        )
        return self.broken_reply if self.broken_reply is not None else result

    def finish(self, control: OperationControl) -> ProcessTermination:
        control.checkpoint()
        self.finishes += 1
        if not self.service.closed:
            raise RuntimeError("Unit worker did not close")
        return ProcessTermination(1, "reaped", 0, False)

    def abort(self, control: OperationControl) -> ProcessTermination:
        control.checkpoint()
        self.aborts += 1
        self.service.close()
        if self.cleanup_failure is not None:
            raise self.cleanup_failure
        return ProcessTermination(1, "reaped", -9, True)


def worker_case(
    root: Path,
) -> tuple[
    ResidentActorEngine,
    Loader,
    ActorPrompt,
    LocalActorParameters,
    OperationControl,
    ActorService,
    UnitChannel,
    SupervisedActorEngine,
]:
    engine, loader, request, parameters, control = setup(root)
    service = ActorService(lambda artifact, config: engine, unit_verifier, unit_guard)
    channel = UnitChannel(service)
    client = SupervisedActorEngine(
        channel, "session", engine.artifact, engine.config, unit_declaration()
    )
    return engine, loader, request, parameters, control, service, channel, client

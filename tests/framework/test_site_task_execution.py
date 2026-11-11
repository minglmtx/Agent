"""Private task boundary: exact scope, once effects and measured readback."""

from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.sites.shopping_admin.tasks.product_execution import (
    AdminProductExecution,
    ProductExecutionInput,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_seed_contract import (
    ProductState,
)
from test_admin_product_seed import seed, record, Commands
from test_admin_description_inputs import FIXTURE, load, reference
from test_admin_services import spec
from test_slurm_commands import guard
from site_worker_fixtures import configuration, operation


def request(
    action: str = "prepare", operation_id: str = "task-prepare"
) -> SiteTaskRequest:
    data = ProductExecutionInput(
        spec=load(FIXTURE.read_bytes()).private_spec, seed=seed()
    )
    return SiteTaskRequest(
        task=data.spec.task,
        binding_ref=reference(b"binding", content_schema="task-binding/1"),
        operation=operation(configuration()).model_copy(
            update={"operation_id": operation_id, "attempt_id": "attempt"}
        ),
        snapshot_ref=(
            None
            if action == "snapshot"
            else reference(
                b"original snapshot", content_schema="admin-product-recovery/2"
            )
        ),
        action=action,  # type: ignore[arg-type]
        private_input=data.model_dump_json(),
    )


def test_prepare_and_inspect_keep_private_input_and_measured_state(
    tmp_path: Path,
) -> None:
    commands = Commands()
    worker = AdminProductExecution(spec(tmp_path), commands)
    first = request()
    first.check_site(configuration())
    result = worker.execute_task(first, control=guard())
    assert result.request_sha256 == first.digest
    assert ProductState.model_validate_json(result.private_result) == record()
    commands.reply = record(description="measured edit").model_dump_json().encode()
    read = request("inspect", "task-read")
    assert (
        ProductState.model_validate_json(
            worker.execute_task(read, control=guard()).private_result
        ).description
        == "measured edit"
    )
    assert len(commands.calls) == 2
    assert '"description"' not in commands.calls[0][-1]


@pytest.mark.parametrize(
    "action,op",
    [
        ("prepare", "task-again"),
        ("prepare", "task-prepare"),
        ("inspect", "task-prepare"),
    ],
)
def test_repeated_effect_or_operation_rejected(
    tmp_path: Path, action: str, op: str
) -> None:
    commands = Commands()
    worker = AdminProductExecution(spec(tmp_path), commands)
    worker.execute_task(request(), control=guard())
    with pytest.raises(InvalidTransition):
        worker.execute_task(request(action, op), control=guard())
    assert len(commands.calls) == 1


@pytest.mark.parametrize(
    "field", ["attempt_id", "allocation_id", "recovery_ref", "run_id", "owner_id"]
)
def test_inspect_cannot_switch_original_scope(tmp_path: Path, field: str) -> None:
    commands = Commands()
    worker = AdminProductExecution(spec(tmp_path), commands)
    worker.execute_task(request(), control=guard())
    read = request("inspect", "task-read")
    value: Any = "different"
    if field == "recovery_ref":
        value = reference(b"other", content_schema="recovery-plan/1")
    read = read.model_copy(
        update={"operation": read.operation.model_copy(update={field: value})}
    )
    with pytest.raises(OwnershipConflict):
        worker.execute_task(read, control=guard())
    assert len(commands.calls) == 1


@pytest.mark.parametrize("kind", ["binding", "input", "task"])
def test_inspect_cannot_switch_binding_or_private_input(
    tmp_path: Path, kind: str
) -> None:
    commands = Commands()
    worker = AdminProductExecution(spec(tmp_path), commands)
    worker.execute_task(request(), control=guard())
    read = request("inspect", "task-read")
    if kind == "binding":
        read = read.model_copy(
            update={"binding_ref": reference(b"other", content_schema="task-binding/1")}
        )
    else:
        data = ProductExecutionInput.model_validate_json(read.private_input)
        if kind == "input":
            data = data.model_copy(
                update={
                    "spec": data.spec.model_copy(update={"description": "different"})
                }
            )
        else:
            task = read.task.model_copy(update={"task_id": "different"})
            data = data.model_copy(
                update={"spec": data.spec.model_copy(update={"task": task})}
            )
            read = read.model_copy(update={"task": task})
        read = read.model_copy(update={"private_input": data.model_dump_json()})
    with pytest.raises(OwnershipConflict):
        worker.execute_task(read, control=guard())
    assert len(commands.calls) == 1


@pytest.mark.parametrize("payload", ["", "{}", "null", "[]", "{broken", " " * 3])
def test_empty_or_malformed_payload_never_calls_native(
    tmp_path: Path, payload: str
) -> None:
    commands = Commands()
    worker = AdminProductExecution(spec(tmp_path), commands)
    with pytest.raises(ValueError):
        worker.execute_task(
            request().model_copy(update={"private_input": payload}), control=guard()
        )
    assert commands.calls == [] and worker.original is None


@pytest.mark.parametrize(
    "kind",
    ["spaces", "duplicate", "family", "task", "empty_products", "extra_products"],
)
def test_noncanonical_or_unsupported_inputs_no_effect(
    tmp_path: Path, kind: str
) -> None:
    commands = Commands()
    worker = AdminProductExecution(spec(tmp_path), commands)
    r = request()
    data = ProductExecutionInput.model_validate_json(r.private_input)
    if kind == "spaces":
        r = r.model_copy(update={"private_input": " " + r.private_input})
    elif kind == "duplicate":
        r = r.model_copy(
            update={
                "private_input": r.private_input.replace(
                    "{", '{"schema_version":"wrong",', 1
                )
            }
        )
    elif kind in ("family", "task"):
        r = r.model_copy(
            update={
                "task": r.task.model_copy(
                    update=(
                        {"family": "unknown"}
                        if kind == "family"
                        else {"task_id": "wrong"}
                    )
                )
            }
        )
    else:
        scenario = data.seed.scenario.model_copy(
            update={
                "products": (
                    () if kind == "empty_products" else data.seed.scenario.products * 2
                )
            }
        )
        data = data.model_copy(
            update={"seed": data.seed.model_copy(update={"scenario": scenario})}
        )
        r = r.model_copy(update={"private_input": data.model_dump_json()})
    with pytest.raises(ValueError):
        worker.execute_task(r, control=guard())
    assert commands.calls == [] and worker.original is None


@pytest.mark.parametrize("kind", ["native_error", "bad_reply", "cancel_after_effect"])
def test_unknown_preparation_cannot_repeat_but_can_inspect(
    tmp_path: Path, kind: str
) -> None:
    commands = Commands()
    worker = AdminProductExecution(spec(tmp_path), commands)
    error = OSError("original native failure")
    if kind == "native_error":
        commands.error = error
    if kind == "bad_reply":
        commands.reply = b"{}"

    class StopAfter:
        def wait(self, seconds: float) -> None:
            self.checkpoint()

        def checkpoint(self) -> float:
            if commands.calls:
                raise TimeoutError("expired after effect")
            return 10.0

    with pytest.raises((OSError, ValueError, TimeoutError)) as caught:
        worker.execute_task(
            request(), control=StopAfter() if kind == "cancel_after_effect" else guard()
        )
    if kind == "native_error":
        assert caught.value is error
    with pytest.raises(InvalidTransition):
        worker.execute_task(request(operation_id="second"), control=guard())
    assert len(commands.calls) == 1
    commands.error = None
    commands.reply = record().model_dump_json().encode()
    read = request("inspect", "read-after-unknown")
    assert worker.execute_task(read, control=guard()).request_sha256 == read.digest
    assert len(commands.calls) == 2


def test_inspect_before_prepare_and_cancel_before_effect(tmp_path: Path) -> None:
    commands = Commands()
    worker = AdminProductExecution(spec(tmp_path), commands)
    with pytest.raises(InvalidTransition):
        worker.execute_task(request("inspect", "read"), control=guard())

    class Stopped:
        def wait(self, seconds: float) -> None:
            self.checkpoint()

        def checkpoint(self) -> float:
            raise TimeoutError("already stopped")

    with pytest.raises(TimeoutError):
        worker.execute_task(request(), control=Stopped())
    assert not commands.calls and worker.original is None
    worker.execute_task(request(), control=guard())


@pytest.mark.parametrize(
    "field,value",
    [
        ("private_input", None),
        ("private_input", {}),
        ("private_input", 123),
        ("action", "delete"),
        ("binding_ref", None),
    ],
)
def test_invalid_request_fields(field: str, value: Any) -> None:
    data = request().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        SiteTaskRequest.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("attempt_id", None),
        ("allocation_id", None),
        ("recovery_ref", None),
        ("mode", "cleanup"),
    ],
)
def test_missing_task_scope_rejected(field: str, value: Any) -> None:
    data = request().model_dump()
    data["operation"][field] = value
    with pytest.raises(ValueError):
        SiteTaskRequest.model_validate(data)


def test_utf8_byte_boundaries_for_private_input_and_result() -> None:
    for value in ("x" * 1048576, "é" * 524288):
        data = request().model_dump()
        data["private_input"] = value
        assert SiteTaskRequest.model_validate(data).private_input == value
        assert (
            SiteTaskResult(request_sha256="0" * 64, private_result=value).private_result
            == value
        )
    for value in ("x" * 1048577, "é" * 524289, "\ud800x"):
        data = request().model_dump()
        data["private_input"] = value
        with pytest.raises(ValueError):
            SiteTaskRequest.model_validate(data)
        with pytest.raises(ValueError):
            SiteTaskResult(request_sha256="0" * 64, private_result=value)


@pytest.mark.parametrize("field", ["run_id", "owner_id", "allocation_id"])
def test_task_check_site_rejects_different_owner(field: str) -> None:
    r = request().model_copy(
        update={"operation": request().operation.model_copy(update={field: "other"})}
    )
    with pytest.raises(OwnershipConflict):
        r.check_site(configuration())

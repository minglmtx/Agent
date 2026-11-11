"""Original reply storage: exact identity, repeat, corrupt history and commit faults."""

import json
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.generator_execution import GeneratorExecutionRecord
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.adapters.models.generator_executions import (
    FileGeneratorExecutions,
)
from lab_generate_skill.adapters.storage.atomic_snapshot import SnapshotTransaction
from lab_generate_skill.adapters.models.generator_worker_protocol import (
    decode_command,
    decode_reply,
)
from generator_execution_fixtures import (
    ExecutionCase,
    e as e,
    execution_template as execution_template,
)
from cgroup_fixtures import Control


def test_publish_reopen_and_exact_repeat(e: ExecutionCase) -> None:
    store = e.adapter
    store.publish(e.record, Control())
    before = {p.name: p.read_bytes() for p in e.root.iterdir()}
    store.publish(e.record, Control())
    assert before == {p.name: p.read_bytes() for p in e.root.iterdir()}
    assert e.adapter.load(e.record.intent, Control()) == e.record
    assert e.adapter.output(e.record, Control()) == e.output


@pytest.mark.parametrize(
    "value", [None, {}, [], True, "record", {"schema_version": "old"}]
)
def test_invalid_record_has_no_index_effects(e: ExecutionCase, value: Any) -> None:
    with pytest.raises(ValidationError):
        e.adapter.publish(value, Control())
    assert not list(e.root.iterdir())


@pytest.mark.parametrize(
    "field",
    [
        "owner",
        "guard",
        "request",
        "parameters",
        "session",
        "sequence",
        "acquired",
        "spec",
        "output",
    ],
)
def test_content_mismatch_before_index_effects(e: ExecutionCase, field: str) -> None:
    record = e.record
    if field == "owner":
        record = record.model_copy(
            update={
                "resource": record.resource.model_copy(
                    update={
                        "owner": record.resource.owner.model_copy(
                            update={"owner_id": "other"}
                        )
                    }
                )
            }
        )
    elif field == "guard":
        record = record.model_copy(
            update={
                "guard": record.guard.model_copy(
                    update={
                        "worker": record.guard.worker.model_copy(
                            update={"start_ticks": 1}
                        )
                    }
                )
            }
        )
    else:
        name = (
            "command_ref"
            if field in ("request", "parameters", "session")
            else "reply_ref"
        )
        if field in ("acquired", "spec"):
            name = field + "_ref"
        ref = getattr(record, name)
        data = json.loads(e.store.read(ref))
        if field == "request":
            data["request"]["request_id"] = "other"
        elif field == "parameters":
            data["parameters"]["max_new_tokens"] = 99
        elif field == "session":
            data["session_id"] = "other"
        elif field == "sequence":
            data["sequence"] += 1
        elif field == "acquired":
            data["kind"] = "closing"
        elif field == "spec":
            data["python_executable"] = "/other/python"
        else:
            data["output"]["completion_tokens"] = 101
        # Re-encode canonically through the original class so failure is semantic.
        if name == "command_ref":
            command = decode_command(e.store.read(ref))
            raw = (
                type(command)
                .model_validate_json(json.dumps(data))
                .model_dump_json()
                .encode()
            )
        elif name == "reply_ref":
            command = decode_command(e.store.read(record.command_ref))
            reply = decode_reply(command, e.store.read(ref))
            raw = (
                type(reply)
                .model_validate_json(json.dumps(data))
                .model_dump_json()
                .encode()
            )
        elif name == "spec_ref":
            from lab_generate_skill.domain.generator_resource import (
                GeneratorResourceSpec,
            )

            raw = (
                GeneratorResourceSpec.model_validate_json(json.dumps(data))
                .model_dump_json()
                .encode()
            )
        else:
            raw = json.dumps(data, sort_keys=True).encode()
        if name == "command_ref":
            # Keep the changed pair internally consistent: rejection must reach
            # original-intent/base-parameter/session checks, not just a digest.
            original_reply = decode_reply(command, e.store.read(record.reply_ref))
            changed_command = decode_command(raw)
            changed_reply = original_reply.model_copy(
                update={
                    "command_sha256": changed_command.digest,
                    "session_id": changed_command.session_id,
                }
            )
            record = record.model_copy(
                update={
                    "reply_ref": e.put(
                        changed_reply.model_dump_json().encode(),
                        record.reply_ref.content_schema,
                    )
                }
            )
        record = record.model_copy(update={name: e.put(raw, ref.content_schema)})
    with pytest.raises((ValueError, OwnershipConflict, EvidenceIntegrityError)):
        e.adapter.publish(record, Control())
    assert not list(e.root.iterdir())


def test_different_valid_reply_cannot_replace_original(e: ExecutionCase) -> None:
    e.adapter.publish(e.record, Control())
    command = decode_command(e.store.read(e.record.command_ref))
    reply = decode_reply(command, e.store.read(e.record.reply_ref))
    changed = reply.model_copy(
        update={"output": e.output.model_copy(update={"text": "different"})}
    )
    record = e.record.model_copy(
        update={
            "reply_ref": e.put(
                changed.model_dump_json().encode(), e.record.reply_ref.content_schema
            )
        }
    )
    with pytest.raises(OwnershipConflict):
        e.adapter.publish(record, Control())
    assert e.adapter.load(e.record.intent, Control()) == e.record


@pytest.mark.parametrize(
    "suffix", ["", ".initialized", ".lock", ".pending-" + "0" * 64]
)
def test_used_history_missing_never_recreated(e: ExecutionCase, suffix: str) -> None:
    e.adapter.publish(e.record, Control())
    name = e.record.intent.key + ".generator-execution.json"
    # Pending filenames are deliberately read from the actual transaction layout.
    if suffix.startswith(".pending"):
        matches = [p for p in e.root.iterdir() if "pending" in p.name]
        assert len(matches) == 1
        matches[0].unlink()
    else:
        (e.root / (name + suffix)).unlink()
    with pytest.raises((EvidenceIntegrityError, FileNotFoundError)):
        e.adapter.load(e.record.intent, Control())
    with pytest.raises(EvidenceIntegrityError):
        e.adapter.publish(e.record, Control())


@pytest.mark.parametrize("when", ["before", "after"])
def test_write_failure_retains_candidate_without_reexecution(
    e: ExecutionCase, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    failure = OSError("commit failed")
    original = SnapshotTransaction.write

    def fail(self: SnapshotTransaction, raw: bytes) -> None:
        if when == "after":
            original(self, raw)
        raise failure

    with monkeypatch.context() as patch:
        patch.setattr(SnapshotTransaction, "write", fail)
        with pytest.raises(OSError) as caught:
            e.adapter.publish(e.record, Control())
    assert (
        caught.value is failure
        and getattr(failure, "generator_execution_candidate") == e.record
    )
    if when == "after":
        assert e.adapter.load(e.record.intent, Control()) == e.record
        e.adapter.publish(e.record, Control())
    else:
        with pytest.raises(EvidenceIntegrityError):
            e.adapter.publish(e.record, Control())


@pytest.mark.parametrize(
    "root", [None, "/tmp", Path("relative"), Path("/tmp/../other")]
)
def test_invalid_root(root: Any, e: ExecutionCase) -> None:
    with pytest.raises(ValueError):
        FileGeneratorExecutions(root, e.store)


def test_parent_path_alias_rejected_without_index_effects(
    e: ExecutionCase, tmp_path: Path
) -> None:
    alias = tmp_path / "alias"
    alias.symlink_to(e.root, target_is_directory=True)
    with pytest.raises(EvidenceIntegrityError):
        FileGeneratorExecutions(alias, e.store).publish(e.record, Control())
    assert not list(e.root.iterdir())

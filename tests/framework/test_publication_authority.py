"""Delegation can only read under the exact still-live original controller."""

import os
from pathlib import Path
import pytest
from lab_generate_skill.adapters.storage import publication_authority as module
from publication_worker_fixtures import inputs, reply
from cgroup_fixtures import Control


@pytest.mark.parametrize(
    "case",
    ["valid", "parent", "ended", "worker", "uid", "deployment", "operation", "switch"],
)
def test_delegated_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    _, snapshot, command = inputs(tmp_path)
    worker = reply(command, snapshot).worker
    monkeypatch.setattr(
        os,
        "getppid",
        lambda: command.scope.writer.process_id if case != "parent" else 1,
    )
    monkeypatch.setattr(
        os,
        "getresuid",
        lambda: (command.scope.execution.uid + (1 if case == "uid" else 0),) * 3,
    )
    monkeypatch.setattr(module, "ended", lambda fd: case == "ended")
    monkeypatch.setattr(
        module,
        "current_process_identity",
        lambda: worker if case != "worker" else command.scope.writer,
    )
    authority = module.DelegatedPublicationAccess(command, worker, 123)
    deployment = (
        command.deployment.model_copy(update={"deployment_id": "other"})
        if case == "deployment"
        else command.deployment
    )
    operation = (
        command.operation.model_copy(update={"operation_id": "other"})
        if case == "operation"
        else command.operation
    )
    if case == "valid":
        authority.authorize_access(deployment, operation, Control())
    else:
        with pytest.raises(RuntimeError):
            if case == "switch":
                authority.authorize_switch(snapshot, snapshot.switches[0], Control())
            else:
                authority.authorize_access(deployment, operation, Control())

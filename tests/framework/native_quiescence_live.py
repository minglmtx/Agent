"""Actual pinned Apptainer namespace leaf; no MySQL, website or snapshot claim."""

import json
import os
import time
from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.native_services import LocalNativeServices
from lab_generate_skill.domain.errors import OperationStopped
from test_admin_database_native import IMAGE
from test_slurm_commands import guard


@pytest.mark.parametrize("mode", ["normal", "ignore_term"])
def test_actual_original_namespace_graceful_or_explicit_unknown(
    tmp_path: Path, mode: str
) -> None:
    assert os.environ.get("SLURM_JOB_ID")
    group = LocalNativeServices(tmp_path)
    script = (
        "trap 'exit 0' TERM; " if mode == "normal" else "trap '' TERM; "
    ) + "printf ready > /state/ready; while :; do sleep 0.05; done"
    started = time.monotonic()
    facts: dict[str, object] = {
        "mode": mode,
        "database_started": False,
        "snapshot_created": False,
    }
    try:
        group.start(
            "mysql",
            (
                "/usr/bin/apptainer",
                "exec",
                "--cleanenv",
                "--containall",
                "--no-home",
                "--no-mount",
                "bind-paths,hostfs,cwd",
                "--pwd",
                "/",
                "--bind",
                str(tmp_path) + ":/state",
                str(IMAGE),
                "/bin/sh",
                "-c",
                script,
            ),
            guard(15),
        )
        ready = guard(15)
        while not (tmp_path / "ready").exists():
            group.require_running()
            ready.wait(0.02)
        pin = group.pin_namespace("mysql", guard(5))
        facts["pin"] = pin.model_dump(mode="json")
        if mode == "normal":
            result = group.quiesce(guard(5))
            facts["quiescence"] = result.model_dump(mode="json")
            assert (
                result.masters[0].returncode == 0
                and not result.masters[0].kill_requested
            )
        else:
            with pytest.raises(OperationStopped):
                group.quiesce(guard(1))
            assert group.quiescence is None and not group.killed
            facts["unknown"] = True
            facts["partial_exits"] = [
                x.model_dump(mode="json") for x in group.observations()
            ]
        with pytest.raises(RuntimeError):
            group.quiesce(guard(5))
    finally:
        # This is the separately bounded failure/physical cleanup path. It
        # cannot turn a failed graceful gate into permission to snapshot.
        for name in tuple(group.namespaces):
            stopped = group.stop_namespace(name, guard(10))
            facts["cleanup_namespace"] = stopped.model_dump(mode="json")
        ending = group.stop(guard(10))
        facts["cleanup_masters"] = [x.model_dump(mode="json") for x in ending]
        facts["elapsed_seconds"] = time.monotonic() - started
        path = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / (
            "namespace-quiescence-" + mode + ".json"
        )
        with path.open("x") as stream:
            json.dump(facts, stream, indent=2)
        assert all(x.state == "reaped" for x in ending)

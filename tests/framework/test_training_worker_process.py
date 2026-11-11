"""Actual isolated installed supervisor/child; no model/tokenizer/training calls."""

from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.session import FramedProcessSession
from lab_generate_skill.adapters.training.worker_client import (
    SupervisedTrainingWorker,
    TrainingWorkerFailure,
)
from lab_generate_skill.adapters.training.worker_protocol import MAX_PACKET
from lab_generate_skill.domain.errors import OwnershipConflict
from training_worker_install_fixtures import prepared_unit_source
from training_worker_fixtures import worker_case, train_command
from actor_installation_fixtures import installed_declaration
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from test_slurm_commands import guard


@pytest.mark.parametrize("mode", ["configure-close", "missing-plan", "foreign-python"])
def test_actual_installed_training_worker_configuration_denial_and_close(
    installed_sources: InstalledFixture, mode: str
) -> None:
    # Existing installation is immutable; writable instance is its own sibling.
    root = installed_sources.workspace / ("unit-sft-" + mode)
    installation = installed_declaration(installed_sources)
    if mode == "foreign-python":
        installation = installation.model_copy(
            update={"python_executable": "/unit-not-the-original-python"}
        )
    c = worker_case(prepared_unit_source(), root, installation)
    # Constructor and configure must work even when no training files/data exist.
    if mode == "missing-plan":
        from lab_generate_skill.domain.evidence_identity import evidence_reference
        from lab_generate_skill.policies.training_metadata import training_metadata

        ref = evidence_reference(
            c.configuration.output.training.model_dump_json().encode(),
            training_metadata("training-plan/1"),
        )
        (Path(c.configuration.evidence_root) / "blobs" / ref.sha256).unlink()
    channel = FramedProcessSession(
        (
            str(installed_sources.executable),
            "-I",
            "-B",
            "-m",
            "lab_generate_skill.bootstrap.training_worker",
        ),
        max_frame_bytes=MAX_PACKET,
    )
    client = SupervisedTrainingWorker(channel, "unit-installed-sft", c.configuration)
    channel.start(guard(30))
    try:
        if mode == "foreign-python":
            with pytest.raises(TrainingWorkerFailure):
                client.configure(guard(30))
            assert (
                client.state == "failed"
                and not Path(c.configuration.output.output_root).exists()
            )
            return
        reply = client.configure(guard(30))
        assert reply.guard is not None and reply.installed is not None
        assert reply.guard.supervisor.process_id == channel.process_id
        assert reply.installed.executable == str(installed_sources.executable)
        assert any(
            m.name == "lab_generate_skill.bootstrap.training_worker"
            for m in reply.installed.modules
        )
        assert not Path(c.configuration.output.output_root).exists()
        if mode == "missing-plan":
            with pytest.raises(TrainingWorkerFailure):
                client.train(train_command(c, client, seconds=30), guard(30))
            assert len(client.exchanges) == 2
            with pytest.raises(OwnershipConflict, match="once-only"):
                client.train(train_command(c, client), guard())
        else:
            ended = client.close(guard(30))
            assert (
                ended.state == "reaped"
                and ended.returncode == 0
                and not ended.kill_requested
            )
            assert client.close(guard()) == ended
            assert channel.capture.complete and not channel.capture.stderr
        assert not Path(c.configuration.output.output_root).exists()
    finally:
        channel.abort(guard(30))

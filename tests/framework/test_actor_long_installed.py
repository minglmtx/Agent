"""Real installed fixed entry accepts explicit2 and closes without loading weights."""

from pathlib import Path
from lab_generate_skill.adapters.models.actor_worker_client import SupervisedActorEngine
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from actor_engine_fixtures import setup
from actor_long_fixtures import long_config
from actor_installation_fixtures import installed_declaration
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)
from worker_install_fixtures import installed_worker as installed_worker
from test_actor_worker_process import channel
from test_slurm_commands import guard


def test_explicit_long_config_in_original_installed_worker_closes_without_weights(
    installed_sources: InstalledFixture, tmp_path: Path
) -> None:
    old, loader, _, _, _ = setup(tmp_path)
    cfg = long_config()
    worker = channel(installed_sources.executable)
    worker.start(guard())
    client = SupervisedActorEngine(
        worker,
        "real-long-config",
        old.artifact,
        cfg,
        installed_declaration(installed_sources),
    )
    try:
        client.configure(guard(30))
        owner, sources = client.owner_guard, client.installed_sources
        assert owner is not None and sources is not None
        assert owner.controller == current_process_identity()
        assert owner.supervisor.process_id == worker.process_id
        assert owner.worker.process_id != worker.process_id
        assert sources.executable == str(installed_sources.executable)
        assert (
            sources.manifest_sha256
            == installed_declaration(installed_sources).manifest_ref.sha256
        )
        assert any(
            m.name == "lab_generate_skill.domain.actor_engine" for m in sources.modules
        )
        assert (
            client.config == cfg
            and client.config.schema_version == "actor-engine-config/2"
        )
        client.configure(guard())
        assert client.owner_guard == owner and client.installed_sources == sources
        client.close(guard())
        ended = worker.capture.termination
        assert ended is not None and ended.state == "reaped"
        assert ended.returncode == 0 and not ended.kill_requested
        assert worker.capture.complete and not worker.capture.stderr
        assert loader.loads == loader.session.calls == 0
    finally:
        worker.abort(guard())


def test_qualified_default_factory_in_same_frozen_installation(
    installed_sources: InstalledFixture, tmp_path: Path
) -> None:
    import ast
    import json
    import subprocess
    from lab_generate_skill.bootstrap.actor_deployment import ACTOR64_INVENTORY_SHA256
    from lab_generate_skill.domain.actor_engine import (
        ActorEngineConfig,
        LocalActorParameters,
    )
    from actor_engine_fixtures import config
    from test_actor_deployment_defaults import documents, reference

    validation, software = documents()
    fixture = Path(__file__).with_name("actor_default_installed_fixture.py")
    ast.parse(fixture.read_text(), filename=str(fixture))
    payload = {
        "config": config().model_dump_json(),
        "inventory": ACTOR64_INVENTORY_SHA256,
        "validation_ref": reference(
            validation, "actor-long-reconciled-acceptance/1"
        ).model_dump_json(),
        "validation": validation.decode(),
        "software_ref": reference(software, "framework-check/3").model_dump_json(),
        "software": software.decode(),
    }
    completed = subprocess.run(
        [str(installed_sources.executable), "-I", "-B", str(fixture)],
        input=json.dumps(payload).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, (completed.stdout, completed.stderr)
    assert not completed.stderr
    result = json.loads(completed.stdout)
    cfg = ActorEngineConfig.model_validate_json(json.dumps(result["config"]))
    params = LocalActorParameters.model_validate_json(json.dumps(result["parameters"]))
    assert cfg == long_config() and (
        cfg.context_window,
        params.max_input_tokens,
        params.max_new_tokens,
    ) == (65536, 61440, 4096)
    assert result["no_torch_import"] and result["changed_proof_rejected"]
    assert Path(result["module"]).is_relative_to(
        installed_sources.executable.parent.parent
    )
    entries = [
        f
        for a in installed_sources.manifest.artifacts
        for f in a.files
        if f.path == "lab_generate_skill/bootstrap/actor_deployment.py"
    ]
    assert len(entries) == 1

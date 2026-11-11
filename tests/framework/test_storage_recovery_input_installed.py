"""Independent new process consumes original durable input after parent death.

This validates recoverable facts, not recovery authority, termination attestation
or permission to clean/restart. The worker scenario verifies actual death itself.
"""

import json
import hashlib
import os
from pathlib import Path
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.capture import require_reaped
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from registered_storage_fixtures import request
from test_registered_storage_parent import (
    test_real_parent_death_stops_native_blocked_registered_writer as parent_death_scenario,
)
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)

CONSUMER = """
import sys,json
from pathlib import Path
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.storage_recovery_input import StorageRecoveryInput
from lab_generate_skill.adapters.processes.worker_identity import current_process_identity
snapshot=EvidenceSessionSnapshot.model_validate_json(Path(sys.argv[1]).read_bytes())
config=EvidenceStorageConfig.model_validate_json(Path(sys.argv[2]).read_bytes())
value=StorageRecoveryInput(snapshot=snapshot,config=config,exchange_id=snapshot.entries[-1].intent.exchange_id)
assert value.intent.controller!=current_process_identity()
assert value.snapshot.entries[-1].outcome is None
sys.stdout.write(json.dumps({"input":value.model_dump(mode="json"),"reader":current_process_identity().model_dump(mode="json")}))
"""


def test_new_process_reads_original_controller_and_descriptor(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    parent_death_scenario(tmp_path, installed_sources)
    frozen = request(tmp_path, installation=installed_sources)
    path = Path(frozen.config.session_root) / (
        frozen.binding.namespace_key + ".evidence-session.json"
    )
    before = {
        p.name: p.read_bytes() for p in Path(frozen.config.session_root).iterdir()
    }
    snapshot = EvidenceSessionSnapshot.model_validate_json(path.read_bytes())
    original = snapshot.entries[-1].intent
    assert original.controller != frozen.controller
    assert original.command == frozen.io
    config_path = tmp_path / "frozen-config.json"
    config_path.write_text(frozen.config.model_dump_json())
    observed = ProcessRunner(max_output_bytes=22 * 1024 * 1024).run(
        (
            str(installed_sources.executable),
            "-I",
            "-B",
            "-c",
            CONSUMER,
            str(path),
            str(config_path),
        ),
        guard(30),
    )
    assert observed.returncode == 0 and not observed.stderr
    packet = json.loads(observed.stdout)
    result = packet["input"]
    reader = packet["reader"]
    assert reader["process_id"] == require_reaped(observed).process_id
    assert reader["process_id"] not in (
        original.controller.process_id,
        original.worker.process_id,
    )
    assert result["snapshot"] == snapshot.model_dump(mode="json")
    assert result["exchange_id"] == original.exchange_id
    assert {
        p.name: p.read_bytes() for p in Path(frozen.config.session_root).iterdir()
    } == before
    assert not (tmp_path / "data" / "blobs").exists()

    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "storage-recovery-input.json"
    ).write_text(
        json.dumps(
            {
                "schema_version": "storage-recovery-input-check/1",
                "original_controller": original.controller.model_dump(mode="json"),
                "original_worker": original.worker.model_dump(mode="json"),
                "reader": reader,
                "exchange_id": original.exchange_id,
                "snapshot_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "config_sha256": frozen.config.sha256,
                "original_command": original.command.model_dump(mode="json"),
                "original_request_digest_retained": original.command_sha256,
                "new_process_only_persistent_inputs": True,
                "original_payload_supplied": False,
                "history_unchanged": True,
                "production_recovery_authority_verified": False,
                "framework_complete": False,
            },
            indent=2,
        )
    )

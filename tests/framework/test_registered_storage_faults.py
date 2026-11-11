"""Actual installed original reply survives outcome-ack and close failure together."""

from pathlib import Path
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.storage.registered_transport import (
    RegisteredStorageTransport,
)
from lab_generate_skill.adapters.storage.registered_protocol import (
    encode_registered_command,
    decode_registered_reply,
)
from registered_storage_fixtures import ExplicitAdmission, request, roots
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)

PROGRAM = """
from lab_generate_skill.adapters.ledger.evidence_sessions import FileEvidenceSessions
from lab_generate_skill.adapters.processes import owner_pidfd
from lab_generate_skill.bootstrap.evidence_worker import main
record=FileEvidenceSessions.record_outcome
close=owner_pidfd.close_owned
def lost(self,*args,**kwargs):
    record(self,*args,**kwargs)
    raise OSError('outcome committed but acknowledgement lost')
def broken(fds,primary=None):
    close(fds,primary)
    failures=([primary] if primary is not None else [])+[OSError('original parent descriptor close report failed')]
    raise BaseExceptionGroup('primary and close',failures)
FileEvidenceSessions.record_outcome=lost
owner_pidfd.close_owned=broken
raise SystemExit(main())
"""


def test_original_reply_survives_commit_ack_and_parent_close_errors(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    roots(tmp_path)
    create = request(tmp_path, create=True, installation=installed_sources)
    RegisteredStorageTransport(
        str(installed_sources.executable), ExplicitAdmission(create)
    ).execute(create, b"", guard(60))
    cmd = request(tmp_path, installation=installed_sources)
    raw = encode_registered_command(cmd, b"evidence")
    capture = ProcessRunner(max_output_bytes=1024 * 1024).run(
        (str(installed_sources.executable), "-I", "-B", "-c", PROGRAM),
        guard(30),
        stdin_bytes=raw,
    )
    assert capture.returncode == 0 and not capture.stderr
    result = decode_registered_reply(raw, capture.stdout)
    assert result.reply.error is not None and len(result.reply.error.children) == 2
    assert (
        result.raw_reply
        and result.reply.intent is not None
        and result.reply.outcome is not None
    )
    assert result.reply.outcome.status == "succeeded" and result.snapshot is None
    assert result.reply.phase == "outcome"
    stored = EvidenceSessionSnapshot.model_validate_json(
        (
            tmp_path
            / "sessions"
            / (cmd.binding.namespace_key + ".evidence-session.json")
        ).read_text()
    )
    assert stored.revision == 2
    assert stored.entries[0].outcome is not None
    assert stored.entries[0].outcome.reply_sha256 == result.reply.outcome.reply_sha256
    assert not stored.entries[0].resolutions

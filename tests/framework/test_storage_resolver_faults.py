"""Actual resolve commit ack loss plus parent close error, then exact readback."""

from pathlib import Path
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.storage.resolver_protocol import (
    encode_resolution_command,
    decode_resolution_reply,
)
from lab_generate_skill.adapters.storage.resolver_transport import (
    StorageResolverTransport,
)
from lab_generate_skill.domain.evidence_session_state import EvidenceSessionSnapshot
from registered_storage_fixtures import ExplicitAdmission
from test_storage_resolver_installed import setup_exchange
from test_slurm_commands import guard
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import (
    InstalledFixture,
    installed_sources as installed_sources,
)

PROGRAM = """
from lab_generate_skill.adapters.ledger.evidence_sessions import FileEvidenceSessions
from lab_generate_skill.adapters.processes import owner_pidfd
from lab_generate_skill.bootstrap.evidence_resolver import main
resolve=FileEvidenceSessions.resolve
close=owner_pidfd.close_owned
def lost(self,*args,**kwargs):
    resolve(self,*args,**kwargs)
    raise OSError('resolution committed but acknowledgement lost')
def broken(fds,primary=None):
    close(fds,primary)
    raise BaseExceptionGroup('primary and close',([primary] if primary is not None else [])+[OSError('parent close report failed')])
FileEvidenceSessions.resolve=lost
owner_pidfd.close_owned=broken
raise SystemExit(main())
"""


def test_original_resolution_survives_commit_and_close_failure_then_replays(
    tmp_path: Path, installed_sources: InstalledFixture
) -> None:
    original, command = setup_exchange(tmp_path, installed_sources)
    raw = encode_resolution_command(command, b"evidence")
    capture = ProcessRunner(max_output_bytes=1024 * 1024).run(
        (str(installed_sources.executable), "-I", "-B", "-c", PROGRAM),
        guard(60),
        stdin_bytes=raw,
    )
    assert capture.returncode == 0 and not capture.stderr
    result = decode_resolution_reply(raw, capture.stdout)
    assert result.reply.error is not None and len(result.reply.error.children) == 2
    assert result.reply.resolution is not None and result.snapshot is None
    path = (
        tmp_path
        / "sessions"
        / (original.binding.namespace_key + ".evidence-session.json")
    )
    before = path.read_bytes()
    stored = EvidenceSessionSnapshot.model_validate_json(before)
    assert stored.revision == 3 and stored.entries[-1].reusable
    assert stored.entries[-1].resolutions[-1] == result.reply.resolution
    (tmp_path / "data").rename(tmp_path / "original-data")
    repeated = StorageResolverTransport(
        str(installed_sources.executable), ExplicitAdmission(original)
    ).execute(command, b"evidence", guard(60))
    assert repeated.result.snapshot == stored and path.read_bytes() == before
    assert repeated.result.reply.resolution == result.reply.resolution

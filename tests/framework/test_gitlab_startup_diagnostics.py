"""Reuse bounded owned-log preservation for the six-service generation layout."""

from gitlab_source_selection import ssh_selection
from pathlib import Path
from typing import Any
import pytest
from shopping_native_diagnostics import retain_startup_logs
from gitlab_site_native_plan import native_configuration, private_site_plan
from site_worker_fixtures import configuration
from site_instance_fixtures import node_path as node_path
from lab_generate_skill.bootstrap.gitlab_instance import gitlab_worker_progress
from lab_generate_skill.sites.gitlab.progress import GitlabPhase


def test_fixed_progress_and_closed_diagnostic_pipe_do_not_hide_operation_errors(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    gitlab_worker_progress(GitlabPhase.SEED_BEGIN)
    assert capsys.readouterr().err.startswith("GITLAB_PHASE seed_begin ")
    private: Any = "caller-private-payload"
    with pytest.raises(ValueError):
        gitlab_worker_progress(private)
    assert capsys.readouterr().err == ""

    class Broken:
        def write(self, value: str) -> None:
            raise OSError("original diagnostic pipe closed")

    monkeypatch.setattr(
        "lab_generate_skill.bootstrap.gitlab_instance.sys.stderr", Broken()
    )
    gitlab_worker_progress(GitlabPhase.SEED_READY)


@pytest.mark.parametrize("case", ["normal", "tail", "link", "repeat", "missing"])
def test_original_gitlab_generation_logs_are_bounded_private_and_not_replayed(
    tmp_path: Path, node_path: Path, case: str
) -> None:
    base = configuration(job_id="4752096")
    private = private_site_plan(
        base.token.owner,
        base.installation,
        evidence_root=tmp_path / "evidence",
        session_root=tmp_path / "sessions",
        journal_root=tmp_path / "journal",
        selection=ssh_selection(),
    )
    files = native_configuration(
        base.installation,
        job_id="4752096",
        parent=node_path / "gitlab",
        private_evidence=private,
    ).files
    root = Path(files.node_root)
    if case != "missing":
        logs = root / "logs/generation-1"
        logs.mkdir(parents=True)
        for service in (
            "postgres",
            "redis",
            "gitaly",
            "puma",
            "workhorse-internal",
            "workhorse-external",
        ):
            (logs / (service + ".log")).write_bytes(
                b"failure\x00\xff" * (40000 if case == "tail" else 1)
            )
        if case == "link":
            (logs / "postgres.log").unlink()
            (logs / "postgres.log").symlink_to(tmp_path / "foreign")
            with pytest.raises(ValueError, match="symlink"):
                retain_startup_logs(files, tmp_path)
            return
    result = retain_startup_logs(files, tmp_path)
    if case == "missing":
        assert result == [
            {"source": "instance", "status": "missing_in_original_job_view"}
        ]
    else:
        assert result[-1] == {
            "source": "runtime",
            "status": "missing_in_original_job_view",
        }
        logs_result = result[:-1]
        assert len(logs_result) == 6 and all(
            r["truncated"] == (case == "tail") for r in logs_result
        )
        for r in logs_result:
            target = tmp_path / "startup-logs" / str(r["source"])
            assert (
                target.stat().st_mode & 0o777 == 0o600
                and target.stat().st_size <= 256 * 1024
            )
        if case == "repeat":
            with pytest.raises(FileExistsError):
                retain_startup_logs(files, tmp_path)

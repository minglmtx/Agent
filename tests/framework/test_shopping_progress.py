"""Fixed phase provenance, exact failure boundaries and bounded private logs."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.shopping_instance import shopping_worker_progress
from lab_generate_skill.sites.shopping.progress import ShoppingPhase as P
from lab_generate_skill.sites.shopping.service_programs import CONFIGURE
from test_shopping_instance import instance
from shopping_native_diagnostics import retain_startup_logs
from shopping_services_fixtures import plan
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


def test_fixed_progress_for_original_preparation_and_native_ready(
    node_path: Path,
) -> None:
    site, commands, groups = instance(node_path)
    phases: list[P] = []
    site.progress = phases.append
    site.prepare(guard())
    site.start(guard())
    assert phases == list(P)
    with pytest.raises(RuntimeError):
        site.prepare(guard())
    assert phases == list(P)


@pytest.mark.parametrize("failure", ["image", "configure"])
def test_failed_phase_never_emits_its_ready_or_repeats_effect(
    node_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    site, commands, groups = instance(node_path)
    phases: list[P] = []
    site.progress = phases.append
    original = commands.run

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError("original failure")

    if failure == "image":
        monkeypatch.setattr(site.files, "stage", fail)
        with pytest.raises(OSError):
            site.prepare(guard())
        assert phases == [P.IMAGE_BEGIN] and not groups
    else:
        site.prepare(guard())

        def command(argv: tuple[str, ...], control: Any) -> bytes:
            if CONFIGURE in argv:
                raise OSError("original configure failure")
            return original(argv, control)

        monkeypatch.setattr(commands, "run", command)
        with pytest.raises(OSError):
            site.start(guard())
        assert phases[-1] == P.CONFIGURE_BEGIN and P.CONFIGURE_READY not in phases
        assert groups[0].names == ["mysql", "redis", "search"]
    assert site.state == "failed"


def test_worker_progress_only_fixed_labels_and_diagnostic_IO_failure(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    shopping_worker_progress(P.IMAGE_BEGIN)
    assert capsys.readouterr().err.startswith("SHOPPING_PHASE image_stage_begin ")
    bad: Any = "caller-private-payload"
    with pytest.raises(ValueError):
        shopping_worker_progress(bad)
    assert capsys.readouterr().err == ""

    class Broken:
        def write(self, value: str) -> None:
            raise OSError("diagnostic pipe closed")

    monkeypatch.setattr(
        "lab_generate_skill.bootstrap.shopping_instance.sys.stderr", Broken()
    )
    shopping_worker_progress(P.IMAGE_READY)


@pytest.mark.parametrize("fault", ["none", "large", "link", "missing"])
def test_original_private_log_tails_no_aliases_and_truthful_missing(
    node_path: Path, tmp_path: Path, fault: str
) -> None:
    root = node_path / "instance"
    selected = plan(root)
    if fault != "missing":
        (root / "logs").mkdir(parents=True)
        log = root / "logs/mysql.log"
        raw = b"x" * (256 * 1024 + 1 if fault == "large" else 20)
        log.write_bytes(raw)
        if fault == "link":
            log.unlink()
            log.symlink_to(tmp_path / "outside")
            with pytest.raises(ValueError):
                retain_startup_logs(selected, tmp_path)
            return
    facts = retain_startup_logs(selected, tmp_path)
    if fault == "missing":
        assert facts == [
            {"source": "instance", "status": "missing_in_original_job_view"}
        ]
    else:
        assert facts[0]["truncated"] == (fault == "large")
        assert (tmp_path / "startup-logs/logs/mysql.log").read_bytes() == raw[
            -256 * 1024 :
        ]

"""Cache boundaries: exact identity, failures, corruption and independent copies."""

import json
from pathlib import Path
import shutil
import pytest
from framework_checks.cache import cache_lock, digest, file_digest
from framework_checks.static import static_checks
from framework_checks.selection import previously_passed
import worker_install_cache as installation


def gate(
    tmp_path: Path,
    *,
    files: dict[str, str] | None = None,
    environment: str = "one",
    fail: bool = False,
    fresh: bool = False,
    changed: bool = False,
) -> tuple[list[dict[str, object]], list[str]]:
    output = tmp_path / str(len(list(tmp_path.glob("run-*"))))
    output = output.with_name("run-" + output.name)
    output.mkdir()
    checks: list[dict[str, object]] = []
    calls: list[str] = []
    original = files or {"src/a.py": "a" * 64, "pyproject.toml": "b" * 64}

    def run(name: str, args: list[str]) -> int:
        calls.append(name)
        (output / f"{name}.log").write_text(name)
        code = int(fail)
        checks.append(
            {"name": name, "command": args, "returncode": code, "execution": "executed"}
        )
        return code

    static_checks(
        cache=tmp_path / "cache",
        output=output,
        files=original,
        format_sources=["src/a.py"],
        environment={"runtime": environment},
        run=run,
        checks=checks,
        current_files=lambda: {} if changed else original,
        fresh=fresh,
    )
    return checks, calls


def test_identical_static_version_reuses_both_gates(tmp_path: Path) -> None:
    _, calls = gate(tmp_path)
    assert calls == ["format_check", "type_check"]
    checks, calls = gate(tmp_path)
    assert calls == [] and [c["execution"] for c in checks] == ["reused", "reused"]
    assert all(Path(str(c["evidence"])).exists() for c in checks)


@pytest.mark.parametrize(
    "reason", ["source", "environment", "force", "failed", "unstable"]
)
def test_nonidentical_or_unaccepted_static_evidence_runs_again(
    tmp_path: Path, reason: str
) -> None:
    gate(tmp_path, fail=reason == "failed", changed=reason == "unstable")
    _, calls = gate(
        tmp_path,
        files={"src/a.py": "c" * 64} if reason == "source" else None,
        environment="two" if reason == "environment" else "one",
        fresh=reason == "force",
    )
    assert calls == ["format_check", "type_check"]


@pytest.mark.parametrize("corruption", ["log", "receipt"])
def test_corrupt_static_evidence_is_not_silently_trusted(
    tmp_path: Path, corruption: str
) -> None:
    gate(tmp_path)
    if corruption == "log":
        (tmp_path / "run-0/type_check.log").write_text("changed")
    else:
        receipt = next((tmp_path / "cache/static").glob("*/receipt.json"))
        value = json.loads(receipt.read_text())
        value["checks"] = []
        receipt.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        gate(tmp_path)


def test_cache_lock_timeout_does_not_replace_live_lock(tmp_path: Path) -> None:
    lock = tmp_path / "lock"
    with cache_lock(lock):
        identity = lock.stat().st_ino
        with pytest.raises(TimeoutError):
            with cache_lock(lock, timeout=0):
                pytest.fail("acquired competing lock")
        assert lock.stat().st_ino == identity
    with cache_lock(lock, timeout=0):
        assert lock.stat().st_ino == identity


def saved_cases(tmp_path: Path) -> Path:
    cases = tmp_path / "selected-cases.json"
    cases.write_text(
        json.dumps(
            {
                "schema_version": "check-cases/1",
                "exitstatus": 0,
                "passed": ["tests/framework/test_a.py::test_one[x]"],
            }
        )
    )
    receipt = tmp_path / "result.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "framework-check/3",
                "passed": True,
                "source_stable_during_checks": True,
                "files": {"source": "a"},
                "environment_key": "env",
                "selected_cases_sha256": file_digest(cases),
            }
        )
    )
    return receipt


def test_exact_passed_nodes_are_deduplicated_and_evidence_retained(
    tmp_path: Path,
) -> None:
    receipt = saved_cases(tmp_path)
    nodes, evidence = previously_passed([receipt, receipt], {"source": "a"}, "env")
    assert nodes == ["tests/framework/test_a.py::test_one[x]"]
    assert evidence[0]["sha256"] == file_digest(receipt)


@pytest.mark.parametrize(
    "change", ["source", "environment", "failed", "cases", "legacy"]
)
def test_passed_cases_require_unchanged_successful_receipts(
    tmp_path: Path, change: str
) -> None:
    receipt = saved_cases(tmp_path)
    data = json.loads(receipt.read_text())
    if change == "failed":
        data["passed"] = False
    if change == "legacy":
        data["schema_version"] = "framework-check/2"
    receipt.write_text(json.dumps(data))
    if change == "cases":
        (tmp_path / "selected-cases.json").write_text("{}")
    with pytest.raises(ValueError):
        previously_passed(
            [receipt],
            {"source": "b" if change == "source" else "a"},
            "other" if change == "environment" else "env",
        )


def fake_install(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    calls: list[Path] = []
    monkeypatch.setattr(
        installation,
        "inputs",
        lambda project: {"source": (project / "source").read_text()},
    )

    def build(project: Path, root: Path) -> None:
        calls.append(root)
        (root / "site-packages").mkdir()
        (root / "site-packages/code.py").write_text((project / "source").read_text())

    monkeypatch.setattr(installation, "build", build)
    return calls


def test_installed_artifact_reuse_and_writable_copy_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_install(monkeypatch)
    (tmp_path / "source").write_text("original")
    artifact, hit, key = installation.prepared_install(tmp_path, tmp_path / "cache")
    assert not hit and len(calls) == 1
    again, hit, second = installation.prepared_install(tmp_path, tmp_path / "cache")
    assert hit and again == artifact and key == second and len(calls) == 1
    copied = tmp_path / "copy.py"
    shutil.copyfile(artifact / "site-packages/code.py", copied)
    copied.write_text("test mutation")
    assert (artifact / "site-packages/code.py").read_text() == "original"
    (tmp_path / "source").write_text("new")
    other, hit, other_key = installation.prepared_install(tmp_path, tmp_path / "cache")
    assert not hit and other != artifact and other_key != key and len(calls) == 2


def test_installed_artifact_corruption_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_install(monkeypatch)
    (tmp_path / "source").write_text("original")
    artifact, _, _ = installation.prepared_install(tmp_path, tmp_path / "cache")
    payload = artifact / "site-packages/code.py"
    payload.chmod(0o644)
    payload.write_text("corrupt")
    with pytest.raises(ValueError, match="cache changed"):
        installation.prepared_install(tmp_path, tmp_path / "cache")


def test_failed_preparation_never_publishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_install(monkeypatch)
    (tmp_path / "source").write_text("original")

    def fail(project: Path, root: Path) -> None:
        (root / "partial").write_text("evidence")
        raise OSError("build failed")

    monkeypatch.setattr(installation, "build", fail)
    with pytest.raises(OSError, match="build failed"):
        installation.prepared_install(tmp_path, tmp_path / "cache")
    assert not (tmp_path / "cache" / digest({"source": "original"})).exists()
    assert len(list((tmp_path / "cache").glob(".building-*/partial"))) == 1

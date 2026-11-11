"""Reuse immutable preparation, isolate writable runtime and verify -I origin."""

import json
import os
from pathlib import Path
import shutil
import sys
import time
import venv
import pytest
from framework_checks.cache import file_digest, tree_files
from worker_install_cache import prepared_install
from worker_install_commands import checked_command as checked_command


@pytest.fixture(scope="session")
def installed_worker(tmp_path_factory: pytest.TempPathFactory) -> Path:
    started = time.monotonic()
    scratch = tmp_path_factory.mktemp("installed-evidence-worker")
    project = Path(__file__).resolve().parents[2]
    artifact, reused, key = prepared_install(
        project, project.parents[1] / "cache/framework-checks/v1/installations"
    )
    runtime = scratch / "runtime"
    venv.EnvBuilder(system_site_packages=True, with_pip=False, symlinks=True).create(
        runtime
    )
    target = (
        runtime
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    # Copy, never hardlink: downstream tests alter modes and sometimes contents.
    shutil.copytree(
        artifact / "site-packages",
        target,
        dirs_exist_ok=True,
        copy_function=shutil.copyfile,
    )
    for path in [target, *target.rglob("*")]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    if tree_files(target) != tree_files(artifact / "site-packages"):
        raise ValueError("Isolated installation copy changed")
    executable = runtime / "bin" / "python"
    raw = checked_command(
        [
            str(executable),
            "-I",
            "-B",
            "-c",
            "import json,sys; import lab_generate_skill.adapters.storage.evidence_worker as m; print(json.dumps({'prefix':sys.prefix,'worker':m.__file__}))",
        ],
        cwd=scratch,
    )
    origin = json.loads(raw)
    assert Path(origin["prefix"]) == runtime
    assert Path(origin["worker"]).is_relative_to(target)
    sources = {
        p: h
        for p, h in tree_files(project / "src/lab_generate_skill").items()
        if p.endswith(".py")
    }
    installed = {
        p: h
        for p, h in tree_files(target / "lab_generate_skill").items()
        if p.endswith(".py")
    }
    assert sources == installed
    (wheel,) = (artifact / "wheels").glob("lab_generate_skill-*.whl")
    receipt = {
        "wheel_sha256": file_digest(wheel),
        "origin": origin,
        "python": str(executable),
        "source_project": str(project),
        "offline": True,
        "production_release": False,
        "installed_python_files_equal_to_source_and_stage": True,
        "files": {"src/lab_generate_skill/" + p: h for p, h in sources.items()},
        "preparation_cache": {
            "key": key,
            "path": str(artifact),
            "reused": reused,
            "receipt_sha256": file_digest(artifact / "receipt.json"),
        },
        "writable_runtime_isolated": True,
        "preparation_seconds": time.monotonic() - started,
    }
    output = os.environ.get("LAB_JOB_OUTPUT_DIRECTORY")
    if output:
        (Path(output) / f"worker-install-{scratch.name}.json").write_text(
            json.dumps(receipt, indent=2) + "\n"
        )
        (Path(output) / "worker-install.json").write_text(
            json.dumps(receipt, indent=2) + "\n"
        )
    return executable

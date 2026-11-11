"""Compile the actual prepared private sources with Node and original Web Ruby.

No Rails startup, DB, Actor or external request. Existing browser proof is reused.
"""

import hashlib
from pathlib import Path
import subprocess
import playwright
from lab_generate_skill.domain.map_runtime_inputs import IMAGE_PINS
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_commands import CheckedNativeCommands
from lab_generate_skill.adapters.processes.capture import CommandFailure
from map_frontend_fixtures import frontend_case
from site_instance_fixtures import node_path
from test_slurm_commands import guard


def test_prepared_private_javascript_and_original_ruby_compile(node_path: Path) -> None:
    spec, files, frontend = frontend_case(node_path)
    receipt = frontend.prepare(guard(60))
    root = Path(spec.inputs.node_tree("frontend"))
    node = Path(playwright.__file__).parent / "driver/node"
    checked = []
    for pin in receipt.changed:
        path = root / pin.path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == pin.sha256
        if path.suffix == ".js":
            result = subprocess.run(
                [str(node), "--check", str(path)],
                capture_output=True,
                timeout=15,
                check=False,
            )
            assert result.returncode == 0, result.stderr.decode()
            checked.append(pin.path)
    assert len(checked) == 6
    sha, size = IMAGE_PINS["web"]
    image = (
        Path("/anvme/workspace/r102bf10-lab-generate-skill/assets/webarena/map/web")
        / sha
        / "web.sif"
    )
    assert image.resolve(strict=True) == image and image.stat().st_size == size
    checksum = hashlib.sha256()
    with image.open("rb") as stream:
        for part in iter(lambda: stream.read(8 * 1024**2), b""):
            checksum.update(part)
    assert checksum.hexdigest() == sha
    argv = (
        "/usr/bin/apptainer",
        "exec",
        "--cleanenv",
        "--containall",
        "--no-home",
        "--no-mount",
        "bind-paths,hostfs,cwd",
        "--bind",
        str(root) + ":/frontend:ro",
        "--pwd",
        "/tmp",
        str(image),
        "ruby",
        "-c",
        "/frontend/app/controllers/api/map_controller.rb",
    )
    try:
        result_bytes = CheckedNativeCommands(ProcessRunner(max_output_bytes=65536)).run(
            argv, guard(30)
        )
    except CommandFailure as error:
        print("original prepared source compile failure", error.capture)
        raise
    assert result_bytes.strip() == b"Syntax OK"
    assert frontend.state == "prepared" and frontend.receipt == receipt

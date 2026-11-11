"""Actual pinned Shopping image read-only inspection; no site or DB startup."""

import hashlib
import json
import os
import stat
import time
from pathlib import Path
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from shopping_image_probe import PROBE, parse_probe
from test_slurm_commands import guard

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
SHA = "455ec7d98aa89b7b63b627aea567f91816d75da50bd160f5db2cc1dfe52f6812"
IMAGE = W / "assets/webarena/shopping" / SHA / "shopping.sif"


def test_original_shopping_image_layout_without_native_services() -> None:
    control = guard(540)
    started = time.monotonic()
    fd = os.open(IMAGE, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_size == 43470442496
        digest = hashlib.sha256()
        while True:
            control.checkpoint()
            part = os.read(fd, 8 * 1024 * 1024)
            if not part:
                break
            digest.update(part)
        after = os.fstat(fd)
        assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        assert digest.hexdigest() == SHA
    finally:
        os.close(fd)
    hash_seconds = time.monotonic() - started
    capture = ProcessRunner(max_output_bytes=16384).run(
        (
            "/usr/bin/apptainer",
            "exec",
            "--cleanenv",
            "--containall",
            "--no-home",
            "--no-mount",
            "bind-paths,hostfs,cwd",
            "--pwd",
            "/",
            str(IMAGE),
            "php",
            "-r",
            PROBE,
        ),
        control,
    )
    assert capture.returncode == 0, capture.stderr.decode(errors="replace")
    result = parse_probe(capture.stdout)
    report = dict(
        image_path=str(IMAGE),
        sha256=SHA,
        size_bytes=before.st_size,
        hash_seconds=hash_seconds,
        probe=result,
        native_services_started=0,
        model_calls=0,
        paid_calls=0,
        read_only=True,
    )
    (
        Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "shopping-image-layout.json"
    ).write_text(json.dumps(report, indent=2) + "\n")
    assert (
        result["pdo_mysql"]
        and all(result["paths"].values())
        and all(result["order_sources"].values())
    ), "Required paths absent; preserve raw layout before deciding native backend"

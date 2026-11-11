"""Engineering probe of original cgroup handles across Slurm deletion, no release claim."""

import json
import os
import time
from pathlib import Path
import pytest
from lab_generate_skill.adapters.models.generator_resource import registered_generator
from generator_resource_fixtures import ResourceCase
from test_generator_resource import c as c, inspect
from worker_install_fixtures import installed_worker as installed_worker
from installed_source_fixtures import installed_sources as installed_sources


def test_original_directory_handle_after_slurm_removal(c: ResourceCase) -> None:
    c.authority.close_denied = True
    fds = []
    readings = []
    try:
        with pytest.raises(BaseExceptionGroup):
            with registered_generator(c.spec, c.op, **c.dependencies()):
                acquired = json.loads(
                    c.evidence.read(inspect(c).events[-1].evidence[0])
                )
                original = acquired["step"]["controller"]["target"]["worker"]
                directory = os.open(
                    original["user_path"], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                )
                fds.append(directory)
                events = os.open(
                    "cgroup.events", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory
                )
                fds.append(events)
                before = os.fstat(directory)
                assert before.st_ino == original["user_inode"]
        for _ in range(30):
            item = os.fstat(directory)
            reading = {
                "inode": item.st_ino,
                "device": item.st_dev,
                "nlink": item.st_nlink,
                "mode": item.st_mode,
                "uid": item.st_uid,
                "gid": item.st_gid,
                "fd_path": os.readlink(f"/proc/self/fd/{directory}"),
            }
            try:
                os.lseek(events, 0, os.SEEK_SET)
                reading["events"] = os.read(events, 4096).decode()
            except OSError as error:
                reading["events_errno"] = error.errno
            readings.append(reading)
            time.sleep(0.05)
        path = (
            Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "cgroup-removal-handles.json"
        )
        path.write_text(
            json.dumps(
                {"original": original, "readings": readings, "release_claim": False},
                indent=2,
            )
            + "\n"
        )
    finally:
        for fd in reversed(fds):
            os.close(fd)

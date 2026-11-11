"""Identity of the pinned development runtime, tools and dependency metadata.

Runtime releases are immutable inputs. Updating their contents in place is not
supported: publish a new runtime path, or bypass reuse with --fresh-static.
This fingerprint is not a fresh verification of every installed dependency byte.
"""

import importlib.metadata
import os
from pathlib import Path
import platform
import sys
from framework_checks.cache import file_digest, tree_files


def environment_identity() -> dict[str, object]:
    distributions = []
    for dist in importlib.metadata.distributions():
        distributions.append(
            {
                "name": dist.metadata["Name"],
                "version": dist.version,
                "location": str(dist.locate_file("")),
                "metadata": dist.read_text("METADATA"),
                "record": dist.read_text("RECORD"),
            }
        )
    # Mypy is supplied through a separate, frozen PYTHONPATH installation.
    extra = {}
    for value in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        path = Path(value)
        if value and (path / "mypy").is_dir():
            extra[str(path.resolve())] = tree_files(path)
    return {
        "python": str(Path(sys.executable).resolve()),
        "python_sha256": file_digest(Path(sys.executable)),
        "base_prefix": sys.base_prefix,
        "version": sys.version,
        "machine": platform.machine(),
        "platform": sys.platform,
        "dependencies": sorted(distributions, key=lambda d: (d["name"], d["location"])),
        "extra_tools": extra,
        "environment": {
            k: os.environ.get(k)
            for k in (
                "PYTHONPATH",
                "PYTHONHOME",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
                "MYPYPATH",
                "MYPY_CONFIG_FILE_DIR",
                "LANG",
                "LC_ALL",
            )
        },
    }

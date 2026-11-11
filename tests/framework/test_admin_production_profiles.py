"""Thin wrapper selection preserves both complete immutable Admin loaders.

No website, model, claim, or source qualification is started here.
"""

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from admin_production_deployment import load_admin_deployment
from admin_production_task_plan import AdminProductionBudgets
from test_slurm_commands import guard

PACKAGE = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/"
    "framework-admin-navigation-production-20261102-v1"
)
WRAPPER = PACKAGE / "production-profile.sbatch"
WRAPPER_SHA256 = "69aa4fabbfc6eeb6e451997bcac6cd63f110821757b831fb342aac333ffaa832"


def selection() -> str:
    assert hashlib.sha256(WRAPPER.read_bytes()).hexdigest() == WRAPPER_SHA256
    raw = WRAPPER.read_text()
    return raw.split("<<'PYSELECT'\n", 1)[1].split("\nPYSELECT\n", 1)[0]


def choose(
    package: Path, partition: str, primary: Path, a40: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            selection(),
            str(package),
            partition,
            str(primary),
            str(a40),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )


def fixtures(root: Path) -> tuple[Path, Path]:
    values = []
    for index, gpu in enumerate(("a100_40gb", "a40")):
        directory = root / ("check-isolated-" + str(index))
        directory.mkdir()
        path = directory / "admin-deployment.json"
        path.write_text(json.dumps({"config": {"long_context": {"gpu_class": gpu}}}))
        values.append(path)
    return values[0], values[1]


@pytest.mark.parametrize("partition,index", [("a100", 0), ("a40", 1)])
def test_original_wrapper_delegates_only_selected_path(
    tmp_path: Path, partition: str, index: int
) -> None:
    paths = fixtures(tmp_path)
    before = [p.read_bytes() for p in paths]
    for _ in range(2):
        result = choose(tmp_path, partition, *paths)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(paths[index])
    assert before == [p.read_bytes() for p in paths]
    text = WRAPPER.read_text()
    original = (PACKAGE / "production.sbatch").read_text()
    # All business execution, signal propagation and cleanup remain canonical.
    assert text.split('"$python_bin" -B ', 1)[1] == original.split(
        '"$python_bin" -B ', 1
    )[1].replace('"$2" &', '"$selected_deployment" &', 1)
    assert "#SBATCH --export=NONE" in text and "[[ $# == 3 ]] || exit 64" in text
    tree = ast.parse(selection())
    assert {
        node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)
    } == {"json", "re", "sys"}


@pytest.mark.parametrize(
    "fault",
    [
        "partition",
        "empty_partition",
        "same",
        "outside",
        "relative",
        "alias",
        "wrong_gpu",
        "missing_config",
        "null_config",
        "empty",
        "corrupt",
    ],
)
def test_bad_profile_refuses_before_canonical_business_entry(
    tmp_path: Path, fault: str
) -> None:
    primary, a40 = fixtures(tmp_path)
    partition = "a40"
    if fault == "partition":
        partition = "rtxpro6k"
    elif fault == "empty_partition":
        partition = ""
    elif fault == "same":
        primary = a40
    elif fault == "outside":
        directory = tmp_path / "outside"
        directory.mkdir()
        primary = directory / primary.name
        primary.write_text("{}")
    elif fault == "relative":
        primary = Path("relative.json")
    elif fault == "alias":
        alias = tmp_path / "check-isolated-22"
        alias.symlink_to(a40.parent, target_is_directory=True)
        a40 = alias / a40.name
    elif fault == "wrong_gpu":
        a40.write_text(
            json.dumps({"config": {"long_context": {"gpu_class": "a100_80gb"}}})
        )
    elif fault == "missing_config":
        a40.write_text("{}")
    elif fault == "null_config":
        a40.write_text('{"config":null}')
    elif fault == "empty":
        a40.write_text("")
    elif fault == "corrupt":
        a40.write_text("{bad")
    result = choose(tmp_path, partition, primary, a40)
    assert result.returncode != 0 and not result.stdout


@pytest.mark.parametrize("partition,job", [("a100", "4908030"), ("a40", "4908390")])
def test_selected_real_immutable_installation_keeps_original_outer_pins(
    partition: str, job: str
) -> None:
    paths = tuple(
        PACKAGE / ("check-isolated-" + value) / "admin-deployment.json"
        for value in ("4908030", "4908390")
    )
    result = choose(PACKAGE, partition, paths[0], paths[1])
    assert result.returncode == 0, result.stderr
    path = Path(result.stdout.strip())
    assert path == PACKAGE / ("check-isolated-" + job) / "admin-deployment.json"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    loaded = load_admin_deployment(path, AdminProductionBudgets(), guard(120))
    config = loaded.frozen.engine_config
    assert config.long_context is not None
    assert config.long_context.gpu_class == (
        "a40" if partition == "a40" else "a100_40gb"
    )
    assert config.context_window == 65536
    assert loaded.parameters.max_input_tokens == 61440
    assert loaded.parameters.max_new_tokens == 4096
    assert before == hashlib.sha256(path.read_bytes()).hexdigest()

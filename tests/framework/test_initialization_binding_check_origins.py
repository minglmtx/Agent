"""Check wrapper namespace only; no current source/site/model/installation grant."""

import importlib
from pathlib import Path
import os


def test_fixed_check_path_keeps_framework_and_outer_consumer_origins() -> None:
    assert os.environ.get("SLURM_JOB_ID")
    workspace = Path("/anvme/workspace/r102bf10-lab-generate-skill")
    source = (
        workspace
        / "code/lab-generate-skill-initialization-input-binding-candidate-20261105/src"
    )
    map_package = (
        workspace / "experiments/framework-map-navigation42-production-20261102-v1"
    )
    admin_package = (
        workspace / "experiments/framework-admin-navigation-production-20261102-v1"
    )
    expected = {
        "production_runtime": map_package
        / "runtime-initialization-input-binding-candidate/production_runtime.py",
        "production_task_plan": map_package
        / "runtime-initialization-input-binding-candidate/production_task_plan.py",
        "admin_production_task_plan": admin_package
        / "runtime-initialization-input-binding-candidate/admin_production_task_plan.py",
        "production_installation": map_package / "production_installation.py",
        "lab_generate_skill.policies.task_initialization": source
        / "lab_generate_skill/policies/task_initialization.py",
        "lab_generate_skill.adapters.sites.task_initialization": source
        / "lab_generate_skill/adapters/sites/task_initialization.py",
    }
    for name, path in expected.items():
        module = importlib.import_module(name)
        assert module.__file__ is not None
        assert Path(module.__file__).resolve() == path.resolve(), name
    # Added roots contain outer files; they do not replace framework namespaces.
    for root in (
        map_package,
        admin_package,
        map_package / "runtime-initialization-input-binding-candidate",
        admin_package / "runtime-initialization-input-binding-candidate",
    ):
        assert not (root / "lab_generate_skill").exists()

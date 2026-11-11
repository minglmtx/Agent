"""Startup probe and task entry share the same fixed image/instance contract."""

from pathlib import Path
from typing import Any
import pytest
from site_resource_native_plan import native_configuration, startup_seconds
from storage_installation_fixtures import storage_installation


@pytest.mark.parametrize(
    "site,expected_size", [("shopping_admin", 1356492800), ("shopping", 43470442496)]
)
def test_fixed_actual_site_plan_no_effects(site: Any, expected_size: int) -> None:
    parent = Path("/tmp/lab-plan-unit")
    config = native_configuration(
        storage_installation(), job_id="1234", parent=parent, site_id=site
    )
    assert config.site_id == site and config.files.image.size_bytes == expected_size
    assert config.files.node_root == str(parent / "instance")
    assert config.files.instance_id == config.token.expected_resource_id
    assert config.token.owner.job_id == "1234"
    assert startup_seconds(site) == (600 if site == "shopping" else 240)


def test_unknown_site_rejected_by_same_configuration_contract() -> None:
    bad: Any = "caller.module"
    with pytest.raises(ValueError):
        native_configuration(
            storage_installation(),
            job_id="1234",
            parent=Path("/tmp/lab-plan-unit"),
            site_id=bad,
        )
    with pytest.raises(ValueError):
        startup_seconds(bad)

"""Validate the exact installed-check declarations before creating a worker."""

from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.site_instance import build_site_instance
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from map_worker_storage_live import missing_input_configuration
from storage_installation_fixtures import storage_installation


def test_missing_input_declarations_are_inert_and_require_live_guard(
    tmp_path: Path,
) -> None:
    cfg = missing_input_configuration(
        storage_installation(),
        job_id="4752096",
        root=tmp_path,
        parent=Path("/tmp/map-installed-preflight-only"),
    )
    assert SiteWorkerConfiguration.model_validate_json(cfg.model_dump_json()) == cfg
    assert cfg.map_inputs is not None and cfg.private_evidence is None
    assert cfg.token.provider_version == "6"
    with pytest.raises(ValueError, match="original live worker guard"):
        build_site_instance(cfg)
    assert not list(tmp_path.iterdir())

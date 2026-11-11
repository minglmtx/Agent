"""Read-only compatibility with all8 original live configurations, no dispatch."""

from pathlib import Path
import json
import pytest
from lab_generate_skill.bootstrap.map_task_configuration import map_task_configuration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.map_origin import MapOriginPolicy
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from map_navigation_group_cases import SOURCES
from source_review_records import ReadOnlyEvidence
from test_slurm_commands import guard

ROOT = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-navigation-actual-batch-20261101-v1"
)


@pytest.mark.parametrize("source", SOURCES)
def test_all8_original_nav1_preserved_and_nav2_origin_is_explicit(
    source: str,
) -> None:
    group = json.loads((ROOT / "actual-group-plan.json").read_bytes())
    original = next(
        row for row in group["all_members"] if row["source_task_id"] == source
    )
    run = ROOT / f"actual-member-{original['actor_job']}"
    actor = json.loads((run / "map-actor-native/facts.json").read_bytes())
    site_path = Path(actor["site_facts_path"])
    assert site_path.resolve(strict=True).is_relative_to(run)
    raw = site_path.read_bytes()
    site = json.loads(raw)
    original_data = site["configuration"]["configuration"]
    assert (
        original_data["map_inputs"]["schema_version"]
        == "map-navigation-worker-inputs/1"
    )
    with pytest.raises(ValueError, match="union_tag_invalid"):
        SiteWorkerConfiguration.model_validate_json(json.dumps(original_data))
    upgraded = json.loads(json.dumps(original_data))
    upgraded["map_inputs"].update(
        schema_version="map-navigation-worker-inputs/2",
        origin=MapOriginPolicy.dynamic().model_dump(),
    )
    expected = SiteWorkerConfiguration.model_validate_json(json.dumps(upgraded))
    inputs = expected.map_inputs
    assert inputs is not None and inputs.scope.task.source_task_id == source
    reader = ReadOnlyEvidence(run / "map-actor-native/resource/evidence")
    request = SiteTaskRequest.model_validate_json(
        reader.read(
            EvidenceRef.model_validate(site["snapshot"]["request"]),
            guard(),
        )
    )
    private = NavigationSpec.model_validate_json(request.private_input)
    assert request.operation.attempt_id == inputs.scope.attempt_id
    current = map_task_configuration(
        inputs.runtime,
        private,
        inputs.scope,
        expected.token,
        expected.installation,
        origin=MapOriginPolicy.dynamic(),
        evidence_root=Path(inputs.evidence_root),
        resource_journal_root=Path(inputs.resource_journal_root),
        artifact_root=Path(inputs.artifact_root),
        max_files=inputs.max_files,
        max_file_bytes=inputs.max_file_bytes,
        max_total_bytes=inputs.max_total_bytes,
    )
    assert current.model_dump_json() == expected.model_dump_json()
    projection = current.model_dump(mode="json")
    projection["map_inputs"].pop("origin")
    projection["map_inputs"]["schema_version"] = "map-navigation-worker-inputs/1"
    assert projection == original_data  # comparison only, never an accepted old wire
    assert site_path.read_bytes() == raw

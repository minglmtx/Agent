"""Complete group semantic/input/full-file coverage, no live site or authority."""

import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.map_artifacts.site_plan import original_site_plan
from lab_generate_skill.adapters.map_artifacts.state_publisher import MapStatePublisher
from lab_generate_skill.adapters.map_artifacts.state_reader import (
    OriginalMapStateReader,
)
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.map.navigation_rules import (
    navigation_outcome,
    original_completion,
)
from lab_generate_skill.bootstrap.map_navigation import load_navigation_inputs
from map_navigation_file_fixtures import navigation_files, DeclaredFilePermission
from map_navigation_fixtures import navigation_case, ORIGIN, ROOT, reference
from map_navigation_group_cases import GROUP_ID, MEMBERS, SOURCES
from test_map_navigation_original_semantics import (
    evaluate_navigation,
    guard_site_result,
)
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize("source,path,heading", MEMBERS, ids=SOURCES)
def test_each_member_exact_native_public_and_derived_lineage(
    source: str, path: str, heading: str
) -> None:
    c = navigation_case(source)
    selected = c.load()
    s = selected.private_spec
    assert s.task.task_id == c.binding.active_task_id
    assert s.task.task_id.startswith(source + "--derived-")
    assert s.task.source_task_id == c.binding.runtime_task_id == source
    assert s.native_contract_ref.sha256 == hashlib.sha256(c.raw).hexdigest()
    assert s.native_contract_ref.size_bytes == len(c.raw)
    assert s.original_start_path == c.native["start_path"]
    assert s.binding.registration_status == c.binding.registration_status
    assert s.goal_revision is not None
    assert not s.goal_revision.original_benchmark_equivalence
    assert s.admission == "unverified" and s.completion.map_route is None
    assert original_completion(s.completion) == c.native["completion"]
    public = selected.public_task.model_dump_json()
    assert selected.public_task.goal == c.native["goal"]
    assert selected.public_task.start_url == ORIGIN + c.native["start_path"]
    assert all(
        k not in public
        for k in (
            "native_contract_ref",
            "admission_result",
            "original_goal",
            "completion",
            "retained_control_review",
        )
    )
    page = dict(
        url=ORIGIN + path,
        http_status=200,
        title="OpenStreetMap",
        heading_texts=[heading],
        login_page=False,
        error_page=False,
    )
    result = navigation_outcome(
        s,
        page,
        site_origin=ORIGIN,
        runtime_error=False,
        selected_records_unchanged=True,
    )
    assert result.status == "success" and result.reward == 1.0


@pytest.mark.parametrize("source,path,heading", MEMBERS, ids=SOURCES)
@pytest.mark.parametrize(
    "case",
    [
        "healthy",
        "wrong-path",
        "wrong-heading",
        "foreign",
        "login",
        "404",
        "503",
        "empty",
        "missing-heading",
        "bool-status",
        "bad-heading-type",
        "runtime-unknown",
        "protected-change",
    ],
)
def test_each_member_original_positive_negative_unknown_and_guard_priority(
    source: str, path: str, heading: str, case: str
) -> None:
    c = navigation_case(source)
    page: Any = dict(
        url=ORIGIN + path,
        http_status=200,
        title="OpenStreetMap",
        heading_texts=[heading],
        login_page=False,
        error_page=False,
    )
    if case == "wrong-path":
        page["url"] = ORIGIN + ("/help" if path != "/help" else "/about")
    elif case == "wrong-heading":
        page["heading_texts"] = ["Different object"]
    elif case == "foreign":
        page["url"] = "http://other:12001" + path
    elif case == "login":
        page["login_page"] = True
    elif case == "404":
        page.update(http_status=404, error_page=True)
    elif case == "503":
        page["http_status"] = 503
    elif case == "empty":
        page = {}
    elif case == "missing-heading":
        page.pop("heading_texts")
    elif case == "bool-status":
        page["http_status"] = True
    elif case == "bad-heading-type":
        page["heading_texts"] = [None]
    error = (
        {"error": "unconfirmed original action"} if case == "runtime-unknown" else None
    )
    protected = case != "protected-change"
    expected = guard_site_result(
        evaluate_navigation(c.native, page, site_origin=ORIGIN),
        runtime_error=error,
        selected_records_unchanged=protected,
    )
    actual = navigation_outcome(
        c.load().private_spec,
        page,
        site_origin=ORIGIN,
        runtime_error=error is not None,
        selected_records_unchanged=protected,
    )
    assert actual.original_result() == expected


@pytest.mark.parametrize("source", SOURCES)
def test_each_member_complete_state_file_binds_its_own_native_task(
    node_path: Path, source: str
) -> None:
    c = navigation_files(node_path, source)
    authority = DeclaredFilePermission(c)
    raw = json.dumps(
        {"synthetic_complete_guard": source, "original_bytes": c.request.private_input},
        sort_keys=True,
    ).encode()
    publisher = MapStatePublisher(c.workspace, authority, authority)
    result = publisher.publish(c.request, raw, "b" * 64, guard())
    authority.read_only = True
    assert result.plan.scope.task.source_task_id == source
    assert result.request_sha256 == c.request.digest
    assert (
        OriginalMapStateReader(c.workspace, authority, authority).read(
            result, c.request, guard()
        )
        == raw
    )
    # A real state file cannot grant a different group member's task or input.
    other = SOURCES[(SOURCES.index(source) + 1) % len(SOURCES)]
    different = navigation_case(other).load().private_spec
    wrong = SiteTaskRequest.model_validate(
        {
            **c.request.model_dump(),
            "task": different.task,
            "private_input": different.model_dump_json(),
        }
    )
    with pytest.raises(OwnershipConflict):
        original_site_plan(c.configuration, wrong)


@pytest.mark.parametrize("source", SOURCES)
def test_each_member_wrong_public_goal_is_rejected_without_dispatch(
    source: str,
) -> None:
    c = navigation_case(source)
    wrong = PublicTask.model_validate(
        {**c.public.model_dump(), "goal": "another declared task"}
    )
    with pytest.raises(EvidenceIntegrityError):
        load_navigation_inputs(c.raw, reference(c.raw), wrong, binding=c.binding)


def test_complete_group_inventory_and_preserved_historical_failures() -> None:
    inventory = json.loads((ROOT / "map-navigation-complete-group.json").read_bytes())
    assert inventory["effective_batch_id"] == GROUP_ID
    assert set(inventory["members"]) == set(SOURCES) and len(inventory["members"]) == 8
    assert not inventory["omitted_members"]
    failures = {
        source
        for source in SOURCES
        if navigation_case(source).binding.registration_status == "failure"
    }
    assert failures == {
        "227f0ce76530eca31eeb",
        "7442ae72bc2576957ca4",
        "eecb7b3837b34a864e11",
    }

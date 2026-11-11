"""Closed-review header/readonly boundary; no actual Admin completion claimed.

Physical source/candidate records below are explicit unit declarations. Complete
resource, Actor, captured evidence, comparison and Reset readers remain original
consumers and must pass on the legal member's actual completed graph.
"""

from copy import deepcopy
import json
import os
from pathlib import Path
from typing import Any
import pytest
import admin_production_review as review_module
from admin_production_review_inputs import completed_admin_review_inputs
from admin_navigation_owned_fixtures import owned_navigation_case
from lab_generate_skill.domain.lifecycle import ResourceRecord, AllocationToken
from lab_generate_skill.domain.state_qualification import EnvironmentSelection
from lab_generate_skill.domain.site_resource import SiteResourceStarted
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.errors import OwnershipConflict
from test_admin_navigation_input import contracts as contracts
from site_instance_fixtures import node_path as node_path


class HeaderAccepted(RuntimeError):
    pass


def record_for(original: ResourceRecord, token: AllocationToken) -> ResourceRecord:
    return ResourceRecord(
        token=token,
        events=tuple(
            event.model_copy(
                update={
                    "operation": event.operation.model_copy(
                        update={
                            "run_id": token.owner.run_id,
                            "owner_id": token.owner.owner_id,
                            "attempt_id": token.attempt_id,
                            "allocation_id": token.allocation_id,
                            "recovery_ref": token.recovery_ref,
                        }
                    )
                }
            )
            for event in original.events
        ),
    )


@pytest.fixture
def facts(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, contracts: Any
) -> dict[str, Any]:
    c = owned_navigation_case(tmp_path, node_path, monkeypatch, contracts)
    source = c.source.qualified.material
    site = c.owned.resources.site.spec
    scope = c.declarations.preparation.scope
    token = c.declarations.reset.attempt_allocations[0]
    browser = BrowserResourceSpec.model_validate(
        source.browser.model_copy(
            update={
                "token": token,
                "configuration": source.browser.configuration.model_copy(
                    update={
                        "spec": source.browser.configuration.spec.model_copy(
                            update={"scope": scope}
                        )
                    }
                ),
            }
        )
    )
    actor = site.token.model_copy(
        update={
            "allocation_id": "unit-actor",
            "resource_kind": "actor",
            "provider_id": "fixed-actor-worker",
            "provider_version": "1",
            "expected_resource_id": "unit-actor",
        }
    )
    env = EnvironmentSelection.model_validate_json(
        c.source.site.evidence.read(c.source.facts.environment_ref)
    )
    started = SiteResourceStarted.model_validate_json(
        c.source.site.evidence.read(env.site_started_ref)
    )
    value = {
        "schema_version": "admin-navigation-owned-closed-review-inputs/1",
        "original_process": os.getpid() + 1,
        "engineering_only": True,
        "site": site.model_dump(mode="json"),
        "browser": browser.model_dump(mode="json"),
        "site_record": record_for(source.site_record, site.token).model_dump(
            mode="json"
        ),
        "browser_record": record_for(source.browser_record, token).model_dump(
            mode="json"
        ),
        "actor_record": record_for(source.site_record, actor).model_dump(mode="json"),
        "started": started.model_dump(mode="json"),
        "evaluation_contract": c.declarations.plan.evaluation.model_dump(mode="json"),
        "source_material": source.model_dump(mode="json"),
        "evidence_root": "/unit-not-read/evidence",
    }
    return value


def test_valid_header_reaches_readonly_store_without_running_any_consumer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    facts: dict[str, Any],
) -> None:
    def stop(root: Path) -> Any:
        raise HeaderAccepted("header accepted; no storage or resource permission")

    monkeypatch.setattr(review_module, "ReadOnlyEvidence", stop)
    path = tmp_path / "review-header.json"
    path.write_text(json.dumps(facts))
    with pytest.raises(HeaderAccepted):
        review_module.review(path)


@pytest.mark.parametrize(
    "fault",
    ["schema", "same-process", "foreign-task", "partial-close", "same-source-root"],
)
def test_foreign_or_partial_header_is_rejected_before_private_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    facts: dict[str, Any],
    fault: str,
) -> None:
    value = deepcopy(facts)
    if fault == "schema":
        value["schema_version"] = "map-owned-closed-review-inputs/1"
    elif fault == "same-process":
        value["original_process"] = os.getpid()
    elif fault == "foreign-task":
        value["evaluation_contract"]["identity"]["source_task_id"] = "foreign"
    elif fault == "partial-close":
        value["actor_record"]["events"].pop()
    else:
        value["source_material"]["site"]["configuration"]["files"]["node_root"] = value[
            "site"
        ]["configuration"]["files"]["node_root"]

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Invalid closed review header touched private storage")

    monkeypatch.setattr(review_module, "ReadOnlyEvidence", forbidden)
    path = tmp_path / "review-header.json"
    path.write_text(json.dumps(value))
    with pytest.raises((ValueError, OwnershipConflict)):
        review_module.review(path)

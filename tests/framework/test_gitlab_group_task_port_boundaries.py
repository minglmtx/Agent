"""Group constructor errors refuse before site/native or cleanup effects."""

import copy
from typing import Any
import pytest

from lab_generate_skill.bootstrap.gitlab_group_task_preparation import (
    gitlab_group_task_preparation,
)
from lab_generate_skill.bootstrap.gitlab_group_task_finalization import (
    gitlab_group_task_finalization,
)
from lab_generate_skill.domain.native_private_json import GITLAB_PRIVATE_JSON
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.task_finalization import TaskFinalizationPlan
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.lifecycle import OperationContext
from gitlab_group_task_port_fixtures import GroupPortCase
from site_instance_fixtures import node_path as node_path
from test_gitlab_group_task_ports import p as p, UnitCleanupRights


class UnusedBindings:
    def publish(self, binding: TaskBinding, op: OperationContext) -> EvidenceRef:
        raise AssertionError("Rejected configuration must not publish bindings")

    def load(self, reference: EvidenceRef, op: OperationContext) -> TaskBinding:
        raise AssertionError("Rejected configuration must not load bindings")


def declaration(p: GroupPortCase) -> TaskFinalizationPlan:
    return TaskFinalizationPlan(
        scope=p.scope,
        browser_close_operation_id="group-close",
        restore_operation_id="group-restore",
        resume_operation_id="group-resume",
        qualification_operation_id="group-reset-facts",
        reset_operation_id="group-safe-reset",
    )


@pytest.mark.parametrize("fault", ["snapshot", "profile", "missing_profile", "version"])
def test_Group_configuration_rejects_foreign_codec_profile_and_family(
    p: GroupPortCase, fault: str
) -> None:
    d, spec = p.declaration, p.resource.spec
    if fault == "snapshot":
        d = d.model_copy(update={"snapshot_schema": "map-navigation-snapshot/1"})
    elif fault in ("profile", "missing_profile"):
        native = spec.configuration.private_evidence
        assert native is not None
        native = (
            None
            if fault == "missing_profile"
            else native.model_copy(update={"profile": GITLAB_PRIVATE_JSON})
        )
        spec = spec.model_copy(
            update={
                "configuration": spec.configuration.model_copy(
                    update={"private_evidence": native}
                )
            }
        )
    else:
        d = d.model_copy(
            update={
                "scope": p.scope.model_copy(
                    update={
                        "task": p.scope.task.model_copy(update={"contract_version": 2})
                    }
                )
            }
        )
    reason = (
        "predeclared complete private evidence storage"
        if fault == "missing_profile"
        else "Group"
    )
    with pytest.raises(ValueError, match=reason):
        gitlab_group_task_preparation(
            p.plan,
            d,
            spec,
            p.site,
            p.resource.journal,
            p.resource.evidence,
            p.resource.controls,
            UnusedBindings(),
            p.authority,
        )
    assert p.site.phase == "new" and not p.requests and not p.resource.channels


def test_Group_finalization_invalid_and_missing_data_has_no_effects(
    p: GroupPortCase,
) -> None:
    right = UnitCleanupRights(p)
    d = declaration(p)

    # This negative boundary performs no evidence writes; wrong data must be
    # rejected before the original declaration reference can be consumed.
    def call(
        plan: Any, declared: Any, preparation: Any, authority: Any = right
    ) -> None:
        gitlab_group_task_finalization(
            plan,
            declared,
            p.plan.declaration_ref,
            p.reset,
            preparation,
            lambda: None,
            p.resource.journal,
            lambda: None,
            authority,
            right,
            right,
            p.resource.evidence,
            p.resource.controls,
        )

    invalid: Any
    for invalid in (None, "", {}, [], 1, True):
        for values in (
            (invalid, d, p.preparation),
            (p.plan, invalid, p.preparation),
            (p.plan, d, invalid),
        ):
            with pytest.raises((TypeError, ValueError)):
                call(*values)
    with pytest.raises(ValueError, match="mandatory"):
        call(p.plan, d, p.preparation, None)
    wrong = copy.copy(p.preparation)
    wrong.declaration = wrong.declaration.model_copy(
        update={"snapshot_schema": "map-navigation-snapshot/1"}
    )
    with pytest.raises(ValueError, match="Group"):
        call(p.plan, d, wrong)
    assert right.unstarted_calls == right.resume_calls == 0
    assert p.site.phase == "new" and not p.requests and not p.resource.channels

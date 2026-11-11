"""Reject counterfeit restored/resumed native facts, never recapture or restore."""

import base64, json
from pathlib import Path
import pytest
from lab_generate_skill.domain.lifecycle import AllocationToken, ClosureReceipt
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.site_resume import SiteResumeResult
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.sites.gitlab.tasks.group_recovery import (
    GroupRestored,
    GroupResumed,
)
from lab_generate_skill.sites.gitlab.tasks.group_capture import GroupCapturePayload
from lab_generate_skill.sites.gitlab.tasks.group_state_checks import GroupStateChecks
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from gitlab_group_qualification_fixtures import qualified, restore
from gitlab_group_preparation_fixtures import put
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("stage", ["restored", "resumed"])
@pytest.mark.parametrize("changed", ["group-row", "project-bytes"])
def test_native_state_drift_cannot_qualify_safe_reset_without_new_effects(
    tmp_path: Path, node_path: Path, stage: str, changed: str
) -> None:
    with qualified(tmp_path, node_path) as c:
        p = c.preparation
        assert p.inputs.request.operation.recovery_ref is not None
        token = AllocationToken(
            allocation_id="browser",
            owner=c.environment.scope.owner,
            scope="attempt",
            attempt_id=c.environment.scope.attempt_id,
            resource_kind="browser",
            expected_resource_id="browser",
            provider_id="fixed-browser-worker",
            provider_version="3",
            recovery_ref=p.inputs.request.operation.recovery_ref,
        )
        closure = ClosureReceipt(
            token=token,
            operation_id="closed",
            status="closed",
            evidence=(c.environment.spec_ref,),
        )
        selected = restore(c, (token,), (put(p.store, closure),))
        task_result = SiteTaskResult.model_validate_json(
            p.store.read(selected.restore_result_ref, guard())
        )
        resume_result = SiteResumeResult.model_validate_json(
            p.store.read(selected.resume_result_ref, guard())
        )
        restored = GroupRestored.model_validate_json(task_result.private_result)
        resumed = GroupResumed.model_validate_json(resume_result.private_result)
        native = restored.native if stage == "restored" else resumed.native
        payload = GroupCapturePayload.model_validate_json(
            p.store.read(native.payload_ref, guard())
        )
        if changed == "project-bytes":
            payload = payload.model_copy(
                update={
                    "project_copy_base64": base64.b64encode(
                        b"forged changed project\n"
                    ).decode()
                }
            )
        else:
            data = json.loads(base64.b64decode(payload.group_reply_base64))
            data["groups"][0]["name"] = "Changed original non-target group"
            payload = payload.model_copy(
                update={
                    "group_reply_base64": base64.b64encode(
                        json.dumps(data).encode()
                    ).decode()
                }
            )
        profile = GITLAB_GROUP_PRIVATE_JSON
        ref = p.store.put(
            payload.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema=profile.content_schema,
                visibility="private",
                producer=profile.producer,
            ),
            guard(),
        )
        native = native.model_copy(update={"payload_ref": ref})
        if stage == "restored":
            changed_task_result = task_result.model_copy(
                update={
                    "private_result": restored.model_copy(
                        update={"native": native}
                    ).model_dump_json()
                }
            )
            selected = selected.model_copy(
                update={"restore_result_ref": put(p.store, changed_task_result)}
            )
        else:
            changed_resume_result = resume_result.model_copy(
                update={
                    "private_result": resumed.model_copy(
                        update={"native": native}
                    ).model_dump_json()
                }
            )
            selected = selected.model_copy(
                update={"resume_result_ref": put(p.store, changed_resume_result)}
            )
        calls = len(p.native.sql.calls)
        generations = len(p.native.task.instance.generations)
        with pytest.raises(OwnershipConflict, match="native (baseline|state)"):
            GroupStateChecks(p.store, load_group_capture).reset(
                selected, put(p.store, selected), guard()
            )
        assert (
            len(p.native.sql.calls) == calls
            and len(p.native.task.instance.generations) == generations == 3
        )

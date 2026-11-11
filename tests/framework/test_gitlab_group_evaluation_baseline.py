"""A complete alternative capture cannot move the original snapshot baseline."""

import base64
import json
from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_group_evaluation import gitlab_group_evaluator
from lab_generate_skill.bootstrap.gitlab_group import load_group_inputs
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.sites.gitlab.tasks.group_recovery import GroupObserved
from lab_generate_skill.sites.gitlab.tasks.group_capture import GroupCapturePayload
from lab_generate_skill.sites.gitlab.group_evaluation_reads import GroupEvaluationReads
from gitlab_group_evaluator_fixtures import evaluation_case
from gitlab_group_preparation_fixtures import put
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize("changed", ["group-row", "project-bytes"])
def test_complete_valid_before_capture_cannot_replace_original_snapshot_baseline(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed: str,
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch) as c:
        p, selected = c.source.preparation, c.selected
        assert selected.before is not None
        result = SiteTaskResult.model_validate_json(
            p.store.read(selected.before.result_ref, guard())
        )
        observed = GroupObserved.model_validate_json(result.private_result)
        payload = GroupCapturePayload.model_validate_json(
            p.store.read(observed.native.payload_ref, guard())
        )
        if changed == "group-row":
            data = json.loads(base64.b64decode(payload.group_reply_base64))
            data["groups"][0]["name"] = "Different complete baseline"
            payload = payload.model_copy(
                update={
                    "group_reply_base64": base64.b64encode(
                        json.dumps(data).encode()
                    ).decode()
                }
            )
        else:
            # Empty original COPY output is valid data, not a missing reply.
            payload = payload.model_copy(update={"project_copy_base64": ""})
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
        changed_observed = observed.model_copy(
            update={"native": observed.native.model_copy(update={"payload_ref": ref})}
        )
        changed_result = result.model_copy(
            update={"private_result": changed_observed.model_dump_json()}
        )
        selected = selected.model_copy(
            update={
                "before": selected.before.model_copy(
                    update={"result_ref": put(p.store, changed_result)}
                )
            }
        )
        calls = len(p.native.sql.calls)
        reads = GroupEvaluationReads(load_group_capture, load_group_inputs)
        with pytest.raises(
            EvidenceIntegrityError, match="shifted original native baseline"
        ):
            reads(c.contract, selected, p.store, guard())
        evaluation = gitlab_group_evaluator(selected).evaluate(
            c.contract, p.store, guard()
        )
        assert evaluation.status == "unknown" and evaluation.reward is None
        assert len(p.native.sql.calls) == calls

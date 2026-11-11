"""Original Group binding/preparation facts, private-state integrity and no queries."""

import base64
from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_group_capture import load_group_capture
from lab_generate_skill.sites.gitlab.tasks.group_preparation_checks import (
    GroupPreparationChecks,
)
from lab_generate_skill.sites.gitlab.tasks.group_recovery import GroupObserved
from lab_generate_skill.sites.gitlab.tasks.group_capture import GroupCapturePayload
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.native_private_json import GITLAB_GROUP_PRIVATE_JSON
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    EvidenceIntegrityError,
    EvidenceNotFound,
    OperationStopped,
)
from gitlab_group_preparation_fixtures import prepared_case
from gitlab_group_fixtures import native_state
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


def test_original_group_binding_and_prepared_publication_recompute_without_new_queries(
    tmp_path: Path, node_path: Path
) -> None:
    with prepared_case(tmp_path, node_path) as c:
        calls = len(c.native.sql.calls)
        publication = c.records.publish(c.inputs.selection, c.inputs.request.operation)
        prepared = c.records.load(publication, c.inputs.request.operation)
        assert c.records.load(publication, c.inputs.request.operation) == prepared
        assert (
            prepared.public_task == c.inputs.public_task
            and prepared.public_task.start_url.endswith("/groups/new")
        )
        assert c.authority.calls >= 3 and len(c.native.sql.calls) == calls
        c.authority.denied = True
        with pytest.raises(PermissionError):
            c.records.load(publication, c.inputs.request.operation)
        assert len(c.native.sql.calls) == calls


@pytest.mark.parametrize(
    "fault",
    [
        "coverage",
        "recovery",
        "private-schema",
        "snapshot",
        "noncanonical",
        "groups",
        "project-bytes",
        "partial",
        "missing-private",
    ],
)
def test_incomplete_or_changed_original_group_preparation_refused(
    tmp_path: Path, node_path: Path, fault: str
) -> None:
    with prepared_case(tmp_path, node_path) as c:
        inputs = c.inputs
        if fault == "coverage":
            inputs = inputs.model_copy(
                update={
                    "spec": inputs.spec.model_copy(
                        update={"preparation_checks": ("reduced",)}
                    )
                }
            )
        elif fault == "recovery":
            inputs = inputs.model_copy(
                update={
                    "recovery": inputs.recovery.model_copy(
                        update={"restore_component_id": "foreign"}
                    )
                }
            )
        elif fault == "private-schema":
            inputs = inputs.model_copy(
                update={
                    "binding": inputs.binding.model_copy(
                        update={
                            "private_spec_ref": inputs.binding.private_spec_ref.model_copy(
                                update={"content_schema": "wrong/1"}
                            )
                        }
                    )
                }
            )
        elif fault == "missing-private":
            (
                node_path
                / "private-evidence/blobs"
                / inputs.binding.private_spec_ref.sha256
            ).unlink()
        elif fault in ("snapshot", "noncanonical"):
            raw = inputs.result.private_result
            if fault == "noncanonical":
                raw = " " + raw
            else:
                observed = GroupObserved.model_validate_json(raw)
                observed = observed.model_copy(
                    update={
                        "snapshot": observed.snapshot.model_copy(
                            update={
                                "request": observed.snapshot.request.model_copy(
                                    update={
                                        "binding_ref": inputs.binding.private_spec_ref
                                    }
                                )
                            }
                        )
                    }
                )
                raw = observed.model_dump_json()
            inputs = inputs.model_copy(
                update={
                    "result": inputs.result.model_copy(update={"private_result": raw})
                }
            )
        else:
            observed = GroupObserved.model_validate_json(inputs.result.private_result)
            native_raw = c.store.read(observed.native.payload_ref, guard())
            payload = GroupCapturePayload.model_validate_json(native_raw)
            if fault == "groups":
                payload = payload.model_copy(
                    update={
                        "group_reply_base64": base64.b64encode(
                            native_state(inserted=True).model_dump_json().encode()
                        ).decode()
                    }
                )
            elif fault == "project-bytes":
                payload = payload.model_copy(
                    update={
                        "project_copy_base64": base64.b64encode(b"changed\n").decode()
                    }
                )
            changed_raw = (
                payload.model_dump_json().encode()
                if fault != "partial"
                else b'{"schema_version":"gitlab-group-partial-capture/1","qualified":false}'
            )
            profile = GITLAB_GROUP_PRIVATE_JSON
            ref = c.store.put(
                changed_raw,
                EvidenceMetadata(
                    media_type="application/json",
                    content_schema=profile.content_schema,
                    visibility="private",
                    producer=profile.producer,
                ),
                guard(),
            )
            observed = observed.model_copy(
                update={
                    "native": observed.native.model_copy(update={"payload_ref": ref})
                }
            )
            inputs = inputs.model_copy(
                update={
                    "result": inputs.result.model_copy(
                        update={"private_result": observed.model_dump_json()}
                    )
                }
            )
        calls = len(c.native.sql.calls)
        with pytest.raises(
            (
                ValueError,
                OwnershipConflict,
                EvidenceIntegrityError,
                EvidenceNotFound,
                FileNotFoundError,
            )
        ):
            GroupPreparationChecks(c.store, load_group_capture).check(inputs, guard())
        assert len(c.native.sql.calls) == calls


def test_cancelled_group_preparation_read_never_queries(
    tmp_path: Path, node_path: Path
) -> None:
    with prepared_case(tmp_path, node_path) as c:
        calls = len(c.native.sql.calls)
        with pytest.raises(OperationStopped):
            GroupPreparationChecks(c.store, load_group_capture).check(
                c.inputs, guard(-1)
            )
        assert len(c.native.sql.calls) == calls

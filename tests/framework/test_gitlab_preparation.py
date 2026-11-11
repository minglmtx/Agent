"""Original binding/private CAS/preparation records and key denial boundaries."""

from pathlib import Path
import pytest
from lab_generate_skill.bootstrap.gitlab_ssh_state import load_ssh_key_state
from lab_generate_skill.sites.gitlab.tasks.ssh_key_preparation_checks import (
    SshKeyPreparationChecks,
)
from lab_generate_skill.sites.gitlab.tasks.ssh_key_recovery import SshKeyObserved
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.sites.gitlab.tasks.ssh_key_spec import SshKeySpec
from gitlab_preparation_fixtures import prepared_case, put
from gitlab_ssh_state_fixtures import native_state
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


def test_original_private_binding_and_prepared_publication_recompute_read_only(
    tmp_path: Path,
    node_path: Path,
) -> None:
    with prepared_case(tmp_path, node_path) as c:
        request = c.inputs.request
        before = c.native.reader.calls
        publication = c.records.publish(c.inputs.selection, request.operation)
        first = c.records.load(publication, request.operation)
        assert c.records.load(publication, request.operation) == first
        assert (
            first.public_task == c.inputs.public_task
            and first.recovery_ref == request.operation.recovery_ref
        )
        assert c.authority.calls >= 3 and c.native.reader.calls == before
        c.authority.denied = True
        with pytest.raises(PermissionError):
            c.records.load(publication, request.operation)
        assert c.native.reader.calls == before


@pytest.mark.parametrize(
    "fault",
    [
        "scope",
        "private_spec",
        "recovery",
        "coverage",
        "native_changed",
        "snapshot",
        "noncanonical",
        "empty",
        "wrong_type",
    ],
)
def test_changed_preparation_cannot_publish_or_narrow_required_coverage(
    tmp_path: Path,
    node_path: Path,
    fault: str,
) -> None:
    with prepared_case(tmp_path, node_path) as c:
        inputs = c.inputs
        if fault == "scope":
            inputs = inputs.model_copy(
                update={
                    "environment": inputs.environment.model_copy(
                        update={
                            "allocation": inputs.environment.allocation.model_copy(
                                update={"allocation_id": "foreign"}
                            )
                        }
                    )
                }
            )
        elif fault == "private_spec":
            private = inputs.binding.private_spec_ref.model_copy(
                update={"content_schema": "wrong/1"}
            )
            inputs = inputs.model_copy(
                update={
                    "binding": inputs.binding.model_copy(
                        update={"private_spec_ref": private}
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
        elif fault == "coverage":
            inputs = inputs.model_copy(
                update={
                    "spec": inputs.spec.model_copy(
                        update={"preparation_checks": ("reduced",)}
                    )
                }
            )
        elif fault == "native_changed":
            observed = SshKeyObserved.model_validate_json(inputs.result.private_result)
            descriptor = c.native.artifacts.publish(
                inputs.request,
                native_state(inserted=True).model_dump_json().encode(),
                control=guard(),
            )
            observed = observed.model_copy(update={"native": descriptor})
            inputs = inputs.model_copy(
                update={
                    "result": inputs.result.model_copy(
                        update={"private_result": observed.model_dump_json()}
                    )
                }
            )
        elif fault == "snapshot":
            request = inputs.request.model_copy(
                update={"snapshot_ref": put(c.store, inputs.spec)}
            )
            inputs = inputs.model_copy(
                update={
                    "request": request,
                    "result": inputs.result.model_copy(
                        update={"request_sha256": request.digest}
                    ),
                }
            )
        else:
            result = inputs.result.model_copy(
                update={
                    "private_result": (
                        " " + inputs.result.private_result
                        if fault == "noncanonical"
                        else "" if fault == "empty" else "[]"
                    )
                }
            )
            inputs = inputs.model_copy(update={"result": result})
        before = c.native.reader.calls
        with pytest.raises((ValueError, OwnershipConflict, EvidenceIntegrityError)):
            SshKeyPreparationChecks(c.store, load_ssh_key_state).check(inputs, guard())
        assert c.native.reader.calls == before


def test_changed_source_parameters_are_refused_before_actual_binding_rights(
    tmp_path: Path,
    node_path: Path,
) -> None:
    with prepared_case(tmp_path, node_path) as c:
        private = SshKeySpec.model_validate_json(c.inputs.request.private_input)
        changed = private.model_copy(
            update={
                "parameters": private.parameters.model_copy(
                    update={"title": "Foreign title"}
                )
            }
        )
        binding = c.inputs.binding.model_copy(
            update={"private_spec_ref": put(c.store, changed)}
        )
        c.authority.denied = True
        with pytest.raises(EvidenceIntegrityError, match="original native contract"):
            c.bindings.publish(binding, c.inputs.request.operation)


def test_cancel_before_private_read_cannot_repeat_native_preparation(
    tmp_path: Path,
    node_path: Path,
) -> None:
    with prepared_case(tmp_path, node_path) as c:

        class Stopped:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "original-preparation-read")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        before = c.native.reader.calls
        with pytest.raises(OperationStopped):
            SshKeyPreparationChecks(c.store, load_ssh_key_state).check(
                c.inputs, Stopped()
            )
        assert c.native.reader.calls == before

"""Read original worker measurements, refuse fabricated native browser account pins."""

from pathlib import Path
import pytest
from lab_generate_skill.sites.gitlab.tasks.ssh_key_browser_binding import (
    SshKeyBrowserChecks,
)
from lab_generate_skill.bootstrap.gitlab_ssh_state import load_ssh_key_state
from lab_generate_skill.domain.site_task import SiteTaskResult
from lab_generate_skill.domain.evidence import EvidenceMetadata
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OwnershipConflict,
    EvidenceNotFound,
)
from gitlab_site_storage_live import missing_asset_configuration
from gitlab_ssh_lifecycle_fixtures import case
from gitlab_browser_initialization_fixtures import selection
from storage_installation_fixtures import storage_installation
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path


def test_new_kind_requires_injected_fixed_semantics_before_any_browser_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prepared_browser_fixtures import prepared_case
    from test_gitlab_ssh_key_inputs import public_task
    from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration

    with prepared_case(tmp_path, monkeypatch) as c:
        config = c.browser.spec.configuration
        selected = selection()
        public = public_task(start_url=selected.endpoint)
        session = config.spec.model_copy(
            update={
                "task": public,
                "scope": config.spec.scope.model_copy(update={"task": public.identity}),
            }
        )
        changed = BrowserWorkerConfiguration.model_validate(
            {**config.model_dump(), "spec": session, "initialization": selected}
        )
        spec = c.browser.spec.model_copy(update={"configuration": changed})
        with pytest.raises(OwnershipConflict, match="requires fixed task checks"):
            c.binding.verify(spec, c.browser.op, guard())
        assert not c.browser.channels


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "account",
        "configuration",
        "guard",
        "instance",
        "request",
        "result",
        "changed_native",
        "missing_native",
        "corrupt_native",
    ],
)
def test_browser_account_is_recomputed_from_complete_original_preparation(
    tmp_path: Path,
    node_path: Path,
    fault: str,
) -> None:
    config = missing_asset_configuration(
        storage_installation(), job_id="4752096", root=tmp_path, parent=node_path
    )
    c = case(node_path, configured=config)
    try:
        c.task.execute_task(c.request, control=guard())
        request = c.next("prepare", "original-prepare")
        result = c.task.execute_task(request, control=guard())
        store = c.artifacts.store
        context = c.artifacts.context
        selected = selection().model_copy(
            update={
                "endpoint": context.instance.endpoint,
                "native_account_id": c.reader.value.account.id,
            }
        )
        instance, owner_guard = context.instance, context.owner_guard
        if fault == "account":
            selected = selected.model_copy(
                update={"native_account_id": selected.native_account_id + 1}
            )
        elif fault == "configuration":
            config = config.model_copy(update={"apptainer": "/usr/bin/foreign"})
        elif fault == "guard":
            owner_guard = owner_guard.model_copy(
                update={
                    "controller": owner_guard.controller.model_copy(
                        update={"start_ticks": owner_guard.controller.start_ticks + 1}
                    )
                }
            )
        elif fault == "instance":
            instance = instance.model_copy(
                update={"endpoint": "http://127.0.0.1:19999/", "ports": (19999,)}
            )
        elif fault == "request":
            request = request.model_copy(
                update={
                    "operation": request.operation.model_copy(
                        update={"operation_id": "foreign"}
                    )
                }
            )
        elif fault == "result":
            result = SiteTaskResult(
                request_sha256="f" * 64, private_result=result.private_result
            )
        elif fault in ("changed_native", "missing_native", "corrupt_native"):
            from lab_generate_skill.sites.gitlab.tasks.ssh_key_recovery import (
                SshKeyObserved,
            )
            from gitlab_ssh_state_fixtures import native_state

            observed = SshKeyObserved.model_validate_json(result.private_result)
            if fault == "changed_native":
                descriptor = c.artifacts.publish(
                    request,
                    native_state(inserted=True).model_dump_json().encode(),
                    control=guard(),
                )
                observed = observed.model_copy(update={"native": descriptor})
                result = result.model_copy(
                    update={"private_result": observed.model_dump_json()}
                )
            else:
                path = (
                    node_path
                    / "private-evidence/blobs"
                    / observed.native.payload_ref.sha256
                )
                if fault == "missing_native":
                    path.unlink()
                else:
                    path.write_bytes(b"corrupted")
        ref = store.put(
            result.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="site-task-result/1",
                visibility="private",
                producer="fixture",
            ),
            guard(),
        )

        def verify() -> None:
            SshKeyBrowserChecks(store, load_ssh_key_state).check_native_account(
                ref,
                request,
                selected,
                config,
                instance,
                owner_guard,
                guard(),
            )

        if fault == "none":
            verify()
            verify()
        elif fault == "missing_native":
            with pytest.raises(EvidenceNotFound):
                verify()
        elif fault == "corrupt_native":
            with pytest.raises(EvidenceIntegrityError):
                verify()
        else:
            with pytest.raises(
                (
                    ValueError,
                    EvidenceIntegrityError,
                    OwnershipConflict,
                    FileNotFoundError,
                )
            ):
                verify()
    finally:
        c.task.instance.stop(guard())

"""New live entry adapters together; only native/Page/kernel effects are doubles."""

from pathlib import Path
from collections.abc import Callable
from typing import Any
import pytest
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.observation import Observation
from map_registered_worker_fixtures import RegisteredMapCase
from map_qualification_fixtures import configure_qualification
from map_qualified_source_native import MapQualifiedSource
from map_source_inputs import MapSourceInputs
from lab_generate_skill.sites.map.tasks.overlay_spec import NativeOverlaySpec
from map_browser_storage_fixtures import collection_spec
from map_browser_collection_fixtures import CollectionCase
from map_terminal_fixtures import select_original
from test_site_resource import enter
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard
import prepared_browser_native


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "wrong-snapshot",
        "missing-closure",
        "actor",
        "actor-native",
        "actor-batch",
        "actor-autopan",
        "actor-protocol-native",
        "actor-protocol-batch",
        "actor-protocol-empty",
    ],
)
def test_same_live_source_preparation_unique_initial_ready_and_safe_reset(
    registered_map: RegisteredMapCase,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    c = registered_map
    assert isinstance(c.private, NativeOverlaySpec)
    proof = select_original(c)
    spec_ref, _ = configure_qualification(c, monkeypatch)
    sources = collection_spec(
        c.workspace / "declared-sources", c.resource.op
    ).original_sources
    inputs = MapSourceInputs(c.configuration, c.private, sources, spec_ref, proof)
    browsers: list[CollectionCase] = []

    def browser(root: Path, patch: pytest.MonkeyPatch, **kwargs: Any) -> Any:
        b = CollectionCase(
            root,
            patch,
            owner=c.scope.owner,
            store=c.resource.evidence,
            workspace=c.workspace,
        )
        if fault == "actor-autopan":
            b.page_fault = "autopan"
            import lab_generate_skill.adapters.browsergym.engine as engine_module

            original_projection: Callable[..., Observation] = getattr(
                engine_module, "project"
            )

            def project(*args: Any, **values: Any) -> Observation:
                observed = original_projection(*args, **values)
                return observed.model_copy(
                    update={
                        "tabs": tuple(
                            tab.model_copy(update={"url": b.page.url})
                            for tab in observed.tabs
                        )
                    }
                )

            patch.setattr(engine_module, "project", project)
        cfg, token = kwargs["config"], kwargs["declared_token"]
        assert cfg.map_inputs is not None
        assert (
            cfg.map_inputs.collection.lifetime_operation.deadline
            == c.resource.op.deadline
        )
        assert (
            cfg.map_inputs.collection.lifetime_operation.parent_operation_id
            == c.resource.op.operation_id
        )
        assert cfg.map_inputs.collection.operation.deadline <= c.resource.op.deadline
        assert (
            cfg.map_inputs.collection.operation.deadline - c.resource.clock.utcnow()
        ).total_seconds() <= 180
        assert kwargs["real_step"] is True  # Only this test substitutes native effects.
        b.configuration = cfg
        b.plan = cfg.map_inputs.plan
        b.resource.spec = BrowserResourceSpec.model_validate(
            b.resource.spec.model_copy(update={"token": token, "configuration": cfg})
        )
        browsers.append(b)
        c.observer = "controller"
        return b.resource

    monkeypatch.setattr(prepared_browser_native, "resource_case", browser)
    monkeypatch.setattr(
        prepared_browser_native,
        "EngineeringTreeAuthority",
        lambda store: browsers[-1].resource.authority,
    )
    with enter(c.resource) as site:
        source = MapQualifiedSource(
            c.resource, site, inputs, allowed_actions=("click", "send_msg_to_user")
        )
        n = source.native
        c.binding, c.task_recovery = n.binding_ref, n.recovery_ref
        if fault.startswith("actor"):
            from map_actual_actor_assembly_fixtures import run_combination

            facts = run_combination(
                c,
                source,
                browsers,
                monkeypatch,
                mode={
                    "actor": "no-request",
                    "actor-native": "native",
                    "actor-batch": "batch",
                    "actor-autopan": "native",
                    "actor-protocol-native": "native",
                    "actor-protocol-batch": "batch",
                    "actor-protocol-empty": "no-request",
                }[fault],
                terminal=fault.startswith("actor-protocol"),
            )
            if fault == "actor-autopan":
                ref = EvidenceRef.model_validate(
                    facts["prepared_browser"]["initial_observation_ref"]
                )
                initial_observed = Observation.model_validate_json(
                    c.resource.evidence.read(ref, control=guard())
                )
                assert initial_observed.sequence == 0
                assert initial_observed.tabs[0].url.endswith("#map=14/40.77/-73.97")
                assert source.native.public.start_url.endswith(
                    "#map=15/40.7695/-73.9738"
                )
            return
        request = c.request("snapshot", "native-task-snapshot")
        result = site.tasks.execute_task(request, control=guard())
        c.snapshot_ref = n.raw(result.private_result.encode(), "map-overlay-snapshot/1")
        c.observer = "controller"
        if fault == "wrong-snapshot":
            with pytest.raises(AssertionError):
                source.after_snapshot(
                    request.model_copy(update={"binding_ref": n.spec_ref}),
                    result,
                    c.snapshot_ref,
                )
            assert "environment_ref" not in source.saved
            return
        source.after_snapshot(request, result, c.snapshot_ref)
        c.observer = "worker"
        request = c.request("prepare", "native-task-prepare")
        result = site.tasks.execute_task(request, control=guard())
        c.observer = "controller"
        publication = n.publish(
            request, result, site.site.instance, environment=source.environment
        )
        observed = source.observe(
            PreparedPublication.model_validate(publication["publication"]),
            c.workspace / "actual-browser",
            monkeypatch,
        )
        assert (
            observed["complete_baseline"] and source.saved["baseline"].status == "ready"
        )
        assert (
            browsers[0].calls.count("navigate") == 1
            and "actual-action" not in browsers[0].calls
        )
        assert source.saved["baseline"].observation_ref == EvidenceRef.model_validate(
            observed["initial_observation_ref"]
        )
        assert source.saved["browser_closed_before_restore"]
        c.observer = "worker"
        restore = c.request("restore", "native-task-restore")
        restored = site.tasks.execute_task(restore, control=guard())
        if fault == "missing-closure":
            source.saved["browser_closed_before_restore"] = False
            with pytest.raises(AssertionError):
                source.after_restore(restore, restored)
            assert (
                c.worker is not None
                and c.worker.tasks is not None
                and c.worker.tasks.phase == "restored"
            )
            return
        # Resume worker observes its original worker identity; qualification reads
        # observe the original controller, as in separate physical processes.
        original_resume = site.resume.resume_frontend

        def resume(*args: Any, **kwargs: Any) -> Any:
            c.observer = "worker"
            try:
                return original_resume(*args, **kwargs)
            finally:
                c.observer = "controller"

        monkeypatch.setattr(site.resume, "resume_frontend", resume)
        c.observer = "controller"
        reset = source.after_restore(restore, restored)
        assert (
            reset["reset_status"] == "safe" and source.saved["reset"].status == "safe"
        )
        assert reset["original_observation_ref"] == observed["initial_observation_ref"]

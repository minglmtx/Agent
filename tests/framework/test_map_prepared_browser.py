"""Original site Task -> preparation -> fixed browser readiness/unique return/close."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.domain.map_browser_collection import MapBrowserPublication
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.domain.browser_initialization import PublicNavigation
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.sites.map.browser_initialization import (
    MapNativeBrowserInitializer,
)
from lab_generate_skill.sites.map.tasks.overlay_browser_binding import (
    OverlayBrowserChecks,
)
from lab_generate_skill.domain.site_task import SiteTaskResult
from map_registered_worker_fixtures import RegisteredMapCase
from map_prepared_records_fixtures import prepare
from map_prepared_browser_fixtures import bind
from preparation_record_fixtures import put
from test_map_registered_worker import registered_map as registered_map
from site_instance_fixtures import node_path as node_path
from test_map_browser_collection import capture
from test_browser_resource import inspect
from test_site_resource import enter
from test_slurm_commands import guard


def test_original_prepared_map_joins_fixed_browser_and_keeps_unique_return(
    registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = registered_map
    with enter(c.resource) as live:
        p = prepare(c, live)
        b, binding, authority = bind(c, p, live, monkeypatch)
        original = binding.task_checks
        assert isinstance(original, OverlayBrowserChecks)
        calls = []

        class ObservedChecks(OverlayBrowserChecks):
            def check(self, *args: Any, **kwargs: Any) -> None:
                calls.append("original-map-check")
                super().check(*args, **kwargs)

        binding.task_checks = ObservedChecks(original.store, original.files)
        c.observer = "controller"
        try:
            with registered_browser(
                b.resource.spec,
                b.resource.op,
                journal=b.resource.journal,
                evidence=b.resource.evidence,
                controls=b.resource.controls,
                clock=b.resource.clock,
                authority=authority,
            ) as browser:
                assert b.engine is not None and isinstance(
                    b.engine.initializer, MapNativeBrowserInitializer
                )
                initial = b.engine.last_readout
                assert (
                    initial is not None
                    and initial.observation.sequence == 0
                    and initial.scope == c.scope
                )
                assert (
                    calls
                    and b.calls.count("project") == 1
                    and b.calls.count("navigate") == 1
                )
                assert b.calls.index("native-view") < b.calls.index("project")
                recorder, request = capture(b, browser)
                recorder.capture(request, control=guard(30))
                assert recorder.result is not None
                publication = MapBrowserPublication.model_validate_json(
                    recorder.result.private_result
                )
                assert publication.sequence == 0 and b.engine.last_readout is initial
            assert (
                inspect(b.resource).state == "closed"
                and b.collector is not None
                and b.collector.native is not None
            )
            assert b.collector.native.requests.relay.physical_closed
            b.participant = "controller"
            reader = MapArtifactReader(
                b.plan, Path(b.plan.workspace_root), b.authority()
            )
            fact = json.loads(
                reader.read(publication.handle, "map-initial-readiness.json", guard())
            )
            assert fact["initialization"][
                "prepared_ref"
            ] == p.publication.prepared_ref.model_dump(mode="json")
            assert (
                fact["native_readiness"]["ready"] is True
                and not fact["task_success_or_admission_claim"]
            )
            assert p.environment.checks.status == "unknown"
            assert p.records.load(p.publication, p.request.operation).scope == c.scope
            assert (
                c.resource.journal.read(c.resource.spec.token, c.resource.op).state
                == "acquired"
            )
        finally:
            c.observer = "worker"
    assert (
        c.resource.journal.read(c.resource.spec.token, c.resource.op).state == "closed"
    )


@pytest.mark.parametrize(
    "fault", ["checks", "public", "prepared", "site", "source", "state"]
)
def test_original_map_binding_rejects_before_browser_spawn(
    fault: str, registered_map: RegisteredMapCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = registered_map
    with enter(c.resource) as live:
        p = prepare(c, live)
        b, binding, authority = bind(c, p, live, monkeypatch)
        if fault == "checks":
            binding.task_checks = None
        if fault == "public":
            cfg = BrowserWorkerConfiguration.model_validate(
                b.configuration.model_copy(
                    update={"initialization": PublicNavigation()}
                )
            )
            b.resource.spec = b.resource.spec.model_copy(update={"configuration": cfg})
        if fault in ("prepared", "site"):
            selected = b.configuration.initialization
            field = "prepared_ref" if fault == "prepared" else "site_ref"
            ref = getattr(selected, field)
            changed_ref = ref.model_copy(update={"producer": "other"})
            if fault == "site":
                changed_ref = put(
                    c.resource.evidence,
                    live.site.model_copy(
                        update={
                            "evidence": live.site.evidence.model_copy(
                                update={"producer": "other"}
                            )
                        }
                    ),
                )
            cfg = b.configuration.model_copy(
                update={
                    "initialization": selected.model_copy(update={field: changed_ref})
                }
            )
            b.resource.spec = b.resource.spec.model_copy(update={"configuration": cfg})
        if fault == "source":
            assert c.configuration.map_inputs is not None
            binding.site_spec = binding.site_spec.model_copy(
                update={
                    "configuration": c.configuration.model_copy(
                        update={
                            "map_inputs": c.configuration.map_inputs.model_copy(
                                update={"private_input_sha256": "f" * 64}
                            )
                        }
                    )
                }
            )
        if fault == "state":
            result = SiteTaskResult(
                request_sha256=p.request.digest,
                private_result=p.observed.model_copy(
                    update={
                        "native": p.observed.native.model_copy(
                            update={
                                "file": p.observed.native.file.model_copy(
                                    update={"sha256": "f" * 64}
                                )
                            }
                        )
                    }
                ).model_dump_json(),
            )
            binding.publication = binding.publication.model_copy(
                update={
                    "selection": binding.publication.selection.model_copy(
                        update={"result_ref": put(c.resource.evidence, result)}
                    )
                }
            )
        c.observer = "controller"
        try:
            with pytest.raises((ValueError, OwnershipConflict, EvidenceIntegrityError)):
                binding.verify(b.resource.spec, b.resource.op, guard())
            assert b.resource.channels == [] and not Path(b.plan.private_root).exists()
        finally:
            c.observer = "worker"

"""Real record/resource graph with synthetic workers, before original reset."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.prepared_browser import PreparedBrowserBinding
from lab_generate_skill.adapters.browsergym.prepared_authority import (
    PreparedBrowserAuthority,
)
from lab_generate_skill.adapters.browsergym.resource import registered_browser
from lab_generate_skill.bootstrap.shopping_order_eta_records import (
    bind_order_eta_records,
)
from lab_generate_skill.bootstrap.shopping_preparation import (
    shopping_preparation_records,
)
from lab_generate_skill.bootstrap.shopping_initial_observation import (
    shopping_initial_observations,
)
from lab_generate_skill.domain.preparation_record import PreparationSelection
from lab_generate_skill.domain.preparation import (
    PreparationReceipt,
    EnvironmentBaseline,
)
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.browser_initialization import ShoppingOrderInitialization
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.baseline import BaselineInputs, assemble_baseline
from lab_generate_skill.domain.observation import Observation
from lab_generate_skill.domain.lifecycle import ClosureReceipt
from lab_generate_skill.domain.errors import OwnershipConflict
from shopping_qualification_fixtures import qualified
from test_shopping_binding_records import UnitBusinessAuthority
from preparation_record_fixtures import put, Authority as PreparationAuthority
from initial_observation_fixtures import Authority as InitialAuthority
from browser_worker_fixtures import configuration
from browser_resource_fixtures import resource_case
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize("fault", ["none", "wrong_site", "wrong_prepared"])
def test_original_shopping_publication_single_view_ready_baseline_and_reset(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    saved: dict[str, Any] = {}

    def before_reset(c: dict[str, Any]) -> ClosureReceipt | None:
        store, site = c["store"], c["c"]
        bindings = bind_order_eta_records(store, site.controls, UnitBusinessAuthority())
        preparations = shopping_preparation_records(
            store, site.controls, bindings, PreparationAuthority()
        )
        selection = PreparationSelection(
            request_ref=put(store, c["prepare"]),
            result_ref=put(store, c["preparation"]),
            environment_ref=c["environment_ref"],
        )
        publication = preparations.publish(selection, c["prepare"].operation)
        prepared = preparations.load(publication, c["prepare"].operation)
        base = configuration(site.spec.configuration.installation)
        spec = BrowserSessionSpec.model_validate(
            {
                **base.spec.model_dump(),
                "scope": prepared.scope,
                "task": prepared.public_task,
            }
        )
        config = BrowserWorkerConfiguration.model_validate(
            {
                **base.model_dump(),
                "spec": spec,
                "initialization": ShoppingOrderInitialization(
                    endpoint=c["live"].site.instance.endpoint,
                    prepared_ref=publication.prepared_ref,
                    site_ref=put(store, c["live"].site),
                ),
            }
        )
        root = tmp_path / "browser"
        root.mkdir()
        b = resource_case(
            root, monkeypatch, config=config, store=store, declared_token=c["browser"]
        )
        joined = PreparedBrowserBinding(
            publication,
            site.spec,
            c["live"].site,
            site.op,
            evidence=store,
            preparations=preparations,
            journal=site.journal,
        )
        if fault == "wrong_site":
            joined.site_spec = joined.site_spec.model_copy(
                update={
                    "configuration": joined.site_spec.configuration.model_copy(
                        update={"site_id": "shopping_admin"}
                    )
                }
            )
        elif fault == "wrong_prepared":
            assert isinstance(config.initialization, ShoppingOrderInitialization)
            b.spec = b.spec.model_copy(
                update={
                    "configuration": config.model_copy(
                        update={
                            "initialization": config.initialization.model_copy(
                                update={
                                    "prepared_ref": publication.prepared_ref.model_copy(
                                        update={"producer": "other"}
                                    )
                                }
                            )
                        }
                    )
                }
            )
        if fault != "none":
            with pytest.raises(OwnershipConflict):
                joined.verify(b.spec, b.op, guard())
            assert not b.channels
            saved["rejected_before_spawn"] = True
            return None
        authority = PreparedBrowserAuthority(b.spec, joined, b.authority)
        with registered_browser(
            b.spec,
            b.op,
            journal=b.journal,
            evidence=store,
            controls=b.controls,
            clock=b.clock,
            authority=authority,
        ) as session:
            assert session.observation_ref is not None
            record = b.journal.read(b.spec.token, b.op)
            intent = ResourceAcquisitionIntent.model_validate_json(
                store.read(record.events[1].evidence[0], control=guard())
            )
            assert session.resource_started_ref is not None
            initial_selection = InitialObservationSelection(
                preparation=publication,
                browser_spec_ref=intent.configuration_ref,
                browser_acquired_ref=session.resource_started_ref,
            )
            initial_records = shopping_initial_observations(
                store, site.controls, preparations, InitialAuthority(initial_selection)
            )
            op = c["prepare"].operation.model_copy(
                update={"operation_id": "shopping-initial-checks"}
            )
            initial_ref = initial_records.publish(initial_selection, op)
            initial = initial_records.load(initial_selection, initial_ref, op)
            environment = EnvironmentBaseline.model_validate_json(
                store.read(c["environment_ref"], control=guard())
            )
            preparation = PreparationReceipt.model_validate_json(
                store.read(publication.preparation_ref, control=guard())
            )
            view = Observation.model_validate_json(
                store.read(session.observation_ref, control=guard())
            )
            inputs = BaselineInputs(
                binding=c["binding"],
                public_task=c["public"],
                spec=c["spec"],
                spec_ref=c["spec_ref"],
                environment=environment,
                environment_ref=c["environment_ref"],
                preparation=preparation,
                preparation_ref=publication.preparation_ref,
                prepared=prepared,
                prepared_ref=publication.prepared_ref,
                observation=view,
                observation_ref=session.observation_ref,
                initial=initial,
                initial_ref=initial_ref,
            )
            baseline = assemble_baseline(
                inputs, op.model_copy(update={"operation_id": "shopping-baseline"})
            )
            assert baseline.status == "ready" and view.sequence == 0
            saved["observation_ref"] = session.observation_ref
            assert b.channels[0].engine.calls == ["start"]
        record = b.journal.read(b.spec.token, b.op)
        assert record.state == "closed"
        fact = json.loads(store.read(record.events[-1].evidence[0], control=guard()))
        return ClosureReceipt.model_validate_json(
            json.dumps(fact["details"]["closure"])
        )

    source_root = tmp_path / "source"
    source_root.mkdir()
    with qualified(source_root, node_path, monkeypatch, before_reset=before_reset) as c:
        reset = c["records"].publish_reset_facts(c["reset_ref"], c["reset_op"])
        assert reset.health.checks.status == "pass"
        assert (
            ("observation_ref" in saved)
            if fault == "none"
            else saved["rejected_before_spawn"]
        )

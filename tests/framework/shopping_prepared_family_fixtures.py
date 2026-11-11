"""Real record/resource graph with synthetic workers, before original reset."""

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from lab_generate_skill.adapters.browsergym.retained_resource import (
    RetainedBrowserResource,
)
from lab_generate_skill.adapters.browsergym.evidence_session import (
    EvidenceBrowserSession,
)
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
from lab_generate_skill.domain.reset import assemble_reset
from lab_generate_skill.domain.evidence import EvidenceRef
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
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.errors import OperationStopped
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.sites.shopping.tasks.navigation_state import (
    CategoryNavigationExecutionInput,
)
from lab_generate_skill.sites.shopping.tasks.navigation_browser_checks import (
    CategoryNavigationBrowserChecks,
)
from lab_generate_skill.bootstrap.shopping_category_records import (
    bind_category_navigation_records,
    category_preparation_records,
    category_initial_observations,
)


def prepared_family_case(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    *,
    category: tuple[bytes, PublicTask] | None = None,
    measure_body_reads: bool = False,
    on_ready: Callable[[dict[str, Any]], None] | None = None,
    on_closed: Callable[[dict[str, Any]], None] | None = None,
    retain_browser: bool = False,
    on_bound: Callable[[dict[str, Any]], ClosureReceipt] | None = None,
    prepare_with: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    on_finished: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    saved: dict[str, Any] = {}

    def before_reset(c: dict[str, Any]) -> ClosureReceipt | None:
        store, site = c["store"], c["c"]
        produced = c.get("recorded_preparation")
        if produced is None:
            binding_authority = (
                UnitBusinessAuthority() if category is None else PreparationAuthority()
            )
            bindings = (
                bind_order_eta_records
                if category is None
                else bind_category_navigation_records
            )(store, site.controls, binding_authority)
            preparation_authority = PreparationAuthority()
            preparations = (
                shopping_preparation_records
                if category is None
                else category_preparation_records
            )(store, site.controls, bindings, preparation_authority)
            selection = PreparationSelection(
                request_ref=put(store, c["prepare"]),
                result_ref=put(store, c["preparation"]),
                environment_ref=c["environment_ref"],
            )
            publication = preparations.publish(selection, c["prepare"].operation)
            prepared = preparations.load(publication, c["prepare"].operation)
        else:
            original_producer = produced["producer"]
            assert original_producer.state.result is not None
            preparation_authority = original_producer.authority
            preparations = original_producer.records
            publication = original_producer.state.result.publication
            prepared = preparations.load(publication, c["prepare"].operation)
            if measure_body_reads:
                raise ValueError(
                    "Existing read-count fixture is only for original standalone records"
                )
        if measure_body_reads:
            read_original = store.read
            reads: Counter[EvidenceRef] = Counter()

            def counted(reference: EvidenceRef, control: Any = None) -> bytes:
                reads[reference] += 1
                raw = read_original(reference, control=control)
                assert type(raw) is bytes
                return raw

            with monkeypatch.context() as counted_patch:
                counted_patch.setattr(store, "read", counted)
                reader = preparations.reader
                preparation_inputs = reader.load(
                    selection, c["prepare"].operation, guard()
                )
                checks = preparations.checks.check(preparation_inputs, guard())
                reader.reads.dependencies((checks,), guard())
                old = dict(reads)
                reads.clear()
                rights = preparation_authority.calls
                actual, receipt = preparations._verify(
                    selection, c["prepare"].operation, guard()
                )
                assert actual == preparation_inputs and receipt.checks == checks
                assert preparation_authority.calls == rights + 1
                assert sum(old.values()) - sum(reads.values()) == 6
                assert preparation_inputs.request.snapshot_ref is not None
                assert (
                    reads[preparation_inputs.binding.private_spec_ref]
                    == reads[preparation_inputs.request.snapshot_ref]
                    == 1
                )
                Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]).joinpath(
                    "category-preparation-read-counts.json"
                ).write_text(
                    json.dumps(
                        {
                            "prior_downstream_reads": sum(old.values()),
                            "current_reads": sum(reads.values()),
                            "private_and_snapshot_reads_each": 1,
                            "dynamic_preparation_authority_calls": 1,
                            "scope": "Same body/dependency verification through actual records over isolated software fixture; authority remains fresh. Not website timing or production grant.",
                        },
                        indent=2,
                    )
                    + "\n"
                )
        base = configuration(site.spec.configuration.installation)
        spec = BrowserSessionSpec.model_validate(
            {
                **base.spec.model_dump(),
                "scope": prepared.scope,
                "task": prepared.public_task,
            }
        )
        site_ref = (
            put(store, c["live"].site)
            if produced is None
            else produced["producer"].state.original_acquired().site_started_ref
        )
        if category is None:
            initialization: (
                ShoppingOrderInitialization | ShoppingCategoryInitialization
            ) = ShoppingOrderInitialization(
                endpoint=c["live"].site.instance.endpoint,
                prepared_ref=publication.prepared_ref,
                site_ref=site_ref,
            )
        else:
            initialization = ShoppingCategoryInitialization(
                endpoint=c["live"].site.instance.endpoint,
                prepared_ref=publication.prepared_ref,
                site_ref=site_ref,
                native_contract_sha256=CategoryNavigationExecutionInput.model_validate_json(
                    c["prepare"].private_input
                ).spec.native_contract_ref.sha256,
            )
        config = BrowserWorkerConfiguration.model_validate(
            {**base.model_dump(), "spec": spec, "initialization": initialization}
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
            task_checks=(
                CategoryNavigationBrowserChecks() if category is not None else None
            ),
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
            assert isinstance(
                config.initialization,
                (ShoppingOrderInitialization, ShoppingCategoryInitialization),
            )
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
        if fault == "missing_task_checks":
            joined.task_checks = None
        if fault == "native_contract":
            assert isinstance(config.initialization, ShoppingCategoryInitialization)
            b.spec = b.spec.model_copy(
                update={
                    "configuration": config.model_copy(
                        update={
                            "initialization": config.initialization.model_copy(
                                update={"native_contract_sha256": "0" * 64}
                            )
                        }
                    )
                }
            )
        if fault == "revoked":
            preparation_authority.denied = True

        class Cancel:
            def checkpoint(self) -> float:
                raise OperationStopped("CANCELLED", "category-browser-binding")

            def wait(self, seconds: float) -> None:
                self.checkpoint()

        if fault != "none":
            expected = (
                PermissionError
                if fault == "revoked"
                else OperationStopped if fault == "cancel" else OwnershipConflict
            )
            with pytest.raises(expected):
                joined.verify(b.spec, b.op, Cancel() if fault == "cancel" else guard())
            assert not b.channels
            saved["rejected_before_spawn"] = True
            return None
        authority = PreparedBrowserAuthority(b.spec, joined, b.authority)
        owner = (
            RetainedBrowserResource(
                b.spec,
                b.op,
                journal=b.journal,
                evidence=store,
                controls=b.controls,
                clock=b.clock,
                authority=authority,
            )
            if retain_browser
            else None
        )
        if on_bound is not None:
            if owner is None or category is None:
                raise ValueError(
                    "Bound initialization requires a fresh retained category browser"
                )
            closure = on_bound(
                dict(
                    c,
                    preparations=preparations,
                    preparation_authority=preparation_authority,
                    publication=publication,
                    prepared=prepared,
                    browser_case=b,
                    browser_owner=owner,
                    prepared_browser=joined,
                )
            )
            assert owner.phase == "closed" and owner.closed is not None
            assert closure.token == owner.spec.token and closure.status == "closed"
            saved["bound_initialization_closed"] = True
            return closure

        @contextmanager
        def original_session() -> Iterator[EvidenceBrowserSession]:
            if owner is None:
                with registered_browser(
                    b.spec,
                    b.op,
                    journal=b.journal,
                    evidence=store,
                    controls=b.controls,
                    clock=b.clock,
                    authority=authority,
                ) as value:
                    yield value
            else:
                with owner as value:
                    yield value

        with original_session() as session:
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
            initial_records = (
                shopping_initial_observations
                if category is None
                else category_initial_observations
            )(store, site.controls, preparations, InitialAuthority(initial_selection))
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
            complete = dict(
                c,
                preparations=preparations,
                preparation_authority=preparation_authority,
                publication=publication,
                prepared=prepared,
                initial_selection=initial_selection,
                initial_checks_ref=initial_ref,
                baseline=baseline,
                browser_case=b,
                browser_owner=owner,
                baseline_inputs=inputs,
                session=session,
            )
            if on_ready is not None:
                on_ready(complete)
        record = b.journal.read(b.spec.token, b.op)
        assert record.state == "closed"
        fact = json.loads(store.read(record.events[-1].evidence[0], control=guard()))
        closure = ClosureReceipt.model_validate_json(
            json.dumps(fact["details"]["closure"])
        )
        if on_closed is not None:
            on_closed(dict(complete, closure=closure))
        return closure

    source_root = tmp_path / "source"
    source_root.mkdir()
    with qualified(
        source_root,
        node_path,
        monkeypatch,
        before_reset=before_reset,
        category=category,
        prepare_with=prepare_with,
    ) as c:
        reset = c["records"].publish_reset_facts(c["reset_ref"], c["reset_op"])
        assert reset.health.checks.status == "pass"
        complete_reset = assemble_reset(reset, c["reset_op"])
        assert complete_reset.status == "safe"
        assert (
            ("observation_ref" in saved or "bound_initialization_closed" in saved)
            if fault == "none"
            else saved["rejected_before_spawn"]
        )
    if on_finished is not None:
        # The original qualified context manager has now closed its site.
        on_finished(dict(c, reset_inputs=reset, reset_receipt=complete_reset))

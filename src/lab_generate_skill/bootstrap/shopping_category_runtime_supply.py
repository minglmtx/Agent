"""Actual original Slurm owner/metadata/model declarations for the category entry.

No site/model/claim permission comes from declarations. Original metadata,
allocation, installed source and later resource authorities still check live.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import json
import tempfile
import time
from typing import Any, ClassVar
from pydantic import ConfigDict
from lab_generate_skill.domain.execution_stage_budget import ExecutionStageBudgets
from lab_generate_skill.application.execution_stage import execution_stage
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.ledger.resource_journal import FileResourceJournal
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from lab_generate_skill.adapters.processes.job_signals import OriginalSignalCancellation
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from lab_generate_skill.adapters.releases.artifact_copy import copy_pinned_file
from lab_generate_skill.adapters.releases.installation import (
    verify_release_installation,
)
from lab_generate_skill.adapters.slurm.allocation import SlurmAllocationVerifier
from lab_generate_skill.adapters.slurm.commands import SlurmCommandRunner
from lab_generate_skill.adapters.slurm.linux_cgroups import observe_current_cgroup
from lab_generate_skill.adapters.slurm.original_execution import original_execution
from lab_generate_skill.adapters.slurm.probe import AccountingSlurmProbe
from lab_generate_skill.adapters.slurm.source_qualification_owner import (
    OriginalSourceQualificationOwner,
)
from lab_generate_skill.domain.actor_engine import (
    ActorEngineConfig,
    LocalActorParameters,
)
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.actor_step import ActorSlurmBinding
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.closed_shopping_source import (
    ClosedCategoryNavigationReadMaterial,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.evidence_sessions import (
    EvidenceSessionBinding,
    EvidenceSessionCapacity,
)
from lab_generate_skill.domain.evidence_storage import EvidenceStorageConfig
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import (
    AllocationToken,
    OperationContext,
    RecoveryPlan,
    ResourceOwner,
)
from lab_generate_skill.domain.operation_window import OperationWindowBudgets
from lab_generate_skill.domain.release import ReleaseArtifact, ReleaseFile
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.shopping_navigation_origin import ShoppingCategoryOrigin
from lab_generate_skill.domain.source_recovery_budget import SourceRecoveryBudgets
from lab_generate_skill.domain.actor_execution_window import ActorGenerationBudgets
from lab_generate_skill.policies.actor_entry_budget import checked_actor_round_budgets
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.storage_scope import OwnerMetadataStorageScope
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.runtime.lifecycle import OperationGuards
from .original_job_time import original_job_controls
from .owner_metadata_store import owner_metadata_store
from .shopping_category_actor_configuration import (
    category_actor_metadata,
    declare_category_actor_inputs,
)
from .shopping_category_navigation import load_category_navigation_inputs
from .shopping_category_source_inputs import CategorySourceReuseInputs
from .shopping_category_source_qualification import CategoryNavigationSourceUnconfirmed
from .shopping_category_production_entry import CategoryNavigationProductionRuntime
from .source_browser_assets import SourceBrowserAssets
from .source_construction_inputs import source_construction_inputs
from .shopping_category_source_artifact import consume_category_navigation_source
from .member_metadata import finish_member_metadata
from lab_generate_skill.sites.shopping.tasks.order_eta_native import SHOPPING_IMAGE_SHA


@dataclass(frozen=True)
class CategoryNavigationSupplierInputs:
    __pydantic_config__: ClassVar[ConfigDict] = ConfigDict(extra="forbid", strict=True)
    installation: ReleaseInstallation
    binding: ActorModelBinding
    engine: ActorEngineConfig
    parameters: LocalActorParameters
    software_ref: EvidenceRef
    software: bytes
    browser_assets: SourceBrowserAssets
    image: ReleaseFile
    image_source: Path
    origin: ShoppingCategoryOrigin
    job_budgets: OperationWindowBudgets
    recovery_budgets: SourceRecoveryBudgets
    site_seconds: int
    task_seconds: int
    setup_seconds: int
    source_metadata_seconds: int
    metadata_cleanup_seconds: int
    physical_close_seconds: int
    generation_seconds: int
    interaction_seconds: int
    actor_cleanup_seconds: int
    template: BrowserWorkerConfiguration | None = None
    stage_budgets: ExecutionStageBudgets | None = None
    generation_budgets: ActorGenerationBudgets | None = None

    def __post_init__(self) -> None:
        if self.generation_budgets is not None:
            if self.stage_budgets is None:
                raise ValueError(
                    "Selected Actor windows require explicit stage budgets"
                )
            checked_actor_round_budgets(
                self.generation_budgets,
                self.generation_seconds,
                self.interaction_seconds,
                self.actor_cleanup_seconds,
                self.stage_budgets.actor_seconds,
            )
        if self.stage_budgets is not None:
            stages = ExecutionStageBudgets.model_validate(self.stage_budgets)
            if (
                stages.source_seconds > self.site_seconds
                or stages.model_seconds != self.setup_seconds
                or stages.task_seconds != self.task_seconds
                or stages.execution_seconds > self.job_budgets.execution_seconds
            ):
                raise ValueError(
                    "Category phase budgets differ from original source/model/task/parent limits"
                )


@dataclass
class SuppliedCategoryNavigationRuntime:
    runtime: CategoryNavigationProductionRuntime
    facts: dict[str, Any]
    cancellation: OriginalSignalCancellation


@contextmanager
def supply_category_runtime(
    selected: CategoryNavigationSupplierInputs,
    raw: bytes,
    native_ref: EvidenceRef,
    public: PublicTask,
    output: Path,
    claim_root: Path,
    *,
    claim_scope: str,
    retained_source: ClosedCategoryNavigationReadMaterial | None = None,
    source_index: Path | None = None,
    source_inputs: CategorySourceReuseInputs | None = None,
) -> Iterator[SuppliedCategoryNavigationRuntime]:
    if not isinstance(selected, CategoryNavigationSupplierInputs):
        raise TypeError("Exact category installed supplier inputs required")
    s = selected
    if source_inputs is not None:
        source_inputs.require(raw, native_ref, public)
        if retained_source is not None and retained_source != source_inputs.material:
            raise OwnershipConflict("Shopping source differs from the selected delta")
        retained_source = source_inputs.material
    installation = ReleaseInstallation.model_validate(s.installation)
    binding = ActorModelBinding.model_validate(s.binding)
    engine = ActorEngineConfig.model_validate(s.engine)
    parameters = LocalActorParameters.model_validate(s.parameters)
    for value, maximum in (
        (s.site_seconds, 7200),
        (s.task_seconds, 14400),
        (s.setup_seconds, 14400),
        (s.source_metadata_seconds, 1800),
        (s.metadata_cleanup_seconds, 3600),
        (s.physical_close_seconds, 60),
        (s.generation_seconds, 600),
        (s.interaction_seconds, 180),
        (s.actor_cleanup_seconds, 60),
    ):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(
                "Explicit bounded category supplier budgets required before effects"
            )
    if s.physical_close_seconds > s.metadata_cleanup_seconds:
        raise ValueError("Metadata cleanup must cover physical category close")
    if retained_source is None and source_index is None:
        raise ValueError(
            "Original category group source checkpoint index is required before construction"
        )
    image = ReleaseFile.model_validate(s.image)
    if image.sha256 != SHOPPING_IMAGE_SHA:
        raise ValueError("Exact original category image is required before staging")
    if (
        not isinstance(s.image_source, Path)
        or s.image_source.resolve(strict=True) != s.image_source
        or not s.image_source.is_relative_to(installation.workspace_root)
        or not s.image_source.is_file()
        or s.image_source.stat().st_size != image.size_bytes
    ):
        raise ValueError(
            "Original canonical workspace category image/file size required before staging"
        )
    native = (
        load_category_navigation_inputs(raw, native_ref, public)
        if source_inputs is None
        else source_inputs.require(raw, native_ref, public)
    )
    models = [
        a
        for a in installation.manifest.artifacts
        if a.artifact_id == binding.model_artifact_id
    ]
    if (
        len(models) != 1
        or binding.release_ref != installation.manifest_ref
        or (s.template is not None and s.template.installation != installation)
    ):
        raise OwnershipConflict(
            "Category supplier changed model/release/browser installation"
        )
    route = evidence_reference(
        binding.model_dump_json().encode(), category_actor_metadata("model-binding/1")
    )
    declare_category_actor_inputs(
        models[0], engine, binding, route, parameters, s.software_ref, s.software
    )
    if (
        public.start_url
        != s.origin.endpoint.rstrip("/") + native.private_spec.original.start_path
    ):
        raise OwnershipConflict("Category supplier changed original public origin")
    for path in (output, claim_root):
        if (
            not isinstance(path, Path)
            or path.resolve(strict=True) != path
            or not path.is_dir()
        ):
            raise ValueError("Original provisioned category output/claim root required")
    if not output.is_relative_to(
        installation.workspace_root
    ) or not claim_root.is_relative_to(installation.workspace_root):
        raise ValueError("Category namespaces must be in the installed workspace")
    execution, accounting = original_execution(
        DeadlineControl(30, "category-original-accounting")
    )
    if output.name != "production-" + execution.job_id:
        raise OwnershipConflict("Category output changed original job identity")
    owner = ResourceOwner(
        run_id="shopping-navigation18-" + execution.job_id,
        owner_id="shopping18-owner",
        job_id=execution.job_id,
        worker_id="shopping18-original-owner",
    )
    from lab_generate_skill.domain.claims import SourceClaimKey

    key = SourceClaimKey(
        scope_id=claim_scope, source_task_id=public.identity.source_task_id
    )
    if next(claim_root.glob(key.filename + "*"), None) is not None:
        raise OwnershipConflict("Original category claim exists; no source/task replay")
    if retained_source is not None:
        retained_source = ClosedCategoryNavigationReadMaterial.model_validate(
            retained_source
        )
        if (
            retained_source.site.token.owner != owner
            or retained_source.site.configuration.installation != installation
        ):
            raise OwnershipConflict(
                "Existing category source cannot inherit another job/installation"
            )
    source_needs = None
    if retained_source is None:
        assert source_index is not None
        source_needs = source_construction_inputs(
            source_index,
            public.identity,
            execution.job_id,
            DeadlineControl(30, "category-source-index"),
            checkpoint_path=(
                "integration_20261103",
                "next_compatible_group",
                "evidence_checkpoints",
            ),
        )
    clock = SystemClock()
    facts: dict[str, Any] = {
        "schema_version": "shopping-category-production-member/1",
        "source_task_id": public.identity.source_task_id,
        "engineering_only": True,
        "formal_training_qualification": False,
        "paid_calls": 0,
        "actual_actor_members_executed": [],
        "source_qualified": False,
        "business_result": "not_executed",
        "independent_review": "not_completed",
        "phase": "metadata",
        "source_construction_inputs": source_needs,
    }
    if source_inputs is not None:
        facts["source_reuse_delta"] = source_inputs.delta
        facts["source_reuse_calls"] = {
            "historical_validator": 0,
            "common_check_or_install": 0,
            "supplier_native_decode": 0,
        }
    managed = None
    primary: BaseException | None = None
    with OriginalSignalCancellation(owner) as cancellation:
        controls, job_time = original_job_controls(
            execution,
            owner,
            current_process_identity().node_id,
            s.job_budgets,
            OperationGuards(clock, cancellation),
            clock,
            DeadlineControl(30, "category-original-job-time"),
        )
        operation = OperationContext(
            operation_id="category.original-owner",
            run_id=owner.run_id,
            owner_id=owner.owner_id,
            cancellation_ref=cancellation.reference,
            deadline=controls.window.execution_deadline,
        )
        if s.stage_budgets is not None:
            controls.configure_stages(operation, s.stage_budgets)
            facts["execution_stage_budgets"] = s.stage_budgets.model_dump(mode="json")
        control = controls.bind(operation)
        try:
            verify_release_installation(installation, control)
            controller = observe_current_cgroup(
                execution, current_process_identity(), control
            ).membership
            scope = StateScope(
                owner=owner,
                task=public.identity,
                attempt_id="execute-" + public.identity.source_task_id,
                context_id="execute-context-" + public.identity.source_task_id,
            )
            source_scope = scope.model_copy(
                update={
                    "attempt_id": "source-only-" + public.identity.source_task_id,
                    "context_id": "source-context-" + public.identity.source_task_id,
                }
            )
            if retained_source is not None and (
                retained_source.site.slurm.parent != controller
                or retained_source.browser.configuration.spec.scope != source_scope
            ):
                raise OwnershipConflict(
                    "Existing category source changed original controller/scope"
                )
            for name in ("evidence", "sessions", "resources", "run", "source-read"):
                path = output / name
                if retained_source is None:
                    path.mkdir(mode=0o700)
                elif not path.is_dir() or path.resolve(strict=True) != path:
                    raise OwnershipConflict(
                        "Existing category source requires its original namespace"
                    )
            config = EvidenceStorageConfig(
                storage_id="shopping18-original-metadata",
                evidence_root=str(output / "evidence"),
                session_root=str(output / "sessions"),
                max_object_bytes=64 * 1024**2,
                capacity=EvidenceSessionCapacity(
                    max_exchanges=10000,
                    max_resolutions_per_exchange=32,
                    max_bytes=8 * 1024**2,
                ),
                installation=installation,
            )
            session = EvidenceSessionBinding(
                storage_id=config.storage_id,
                scope="run",
                source_task_id=None,
                session_id="shopping18-original-" + execution.job_id,
                owner=owner,
                release_id=installation.manifest.release_id,
                storage_config_sha256=config.sha256,
            )
            storage = OwnerMetadataStorageScope(
                binding=session,
                config=config,
                writer=controller.writer,
                execution=execution,
                workspace_root=installation.workspace_root,
            )
            activation = operation.model_copy(
                update={
                    "operation_id": "category.metadata.initialize",
                    "cancellation_ref": None,
                }
            )
            managed = owner_metadata_store(
                storage,
                activation,
                clock,
                controls,
                controls.bind(activation),
                max_io_seconds=30,
                cleanup_seconds=60,
            )
            snapshot = (
                managed.store.initialize(controls.bind(activation))
                if retained_source is None
                else managed.store.open_existing(controls.bind(activation))
            )
            facts.update(
                metadata_initialized=True,
                metadata_initial_revision=snapshot.revision,
                metadata_open_mode=(
                    "initialize" if retained_source is None else "existing_only"
                ),
                job_time_limit=job_time.limit.model_dump(mode="json"),
                job_time_window=controls.window.model_dump(mode="json"),
            )
            store = managed.store

            def put(body: bytes, schema: str) -> EvidenceRef:
                metadata = category_actor_metadata(schema)
                expected = evidence_reference(body, metadata)
                actual = store.put(body, metadata, control=control)
                if actual != expected:
                    raise OwnershipConflict(
                        "Category supplier publication changed canonical bytes"
                    )
                return actual

            for body, schema in (
                (
                    installation.manifest.model_dump_json().encode(),
                    installation.manifest.schema_version,
                ),
                (binding.model_dump_json().encode(), "model-binding/1"),
                (engine.model_dump_json().encode(), engine.schema_version),
                (s.software, "framework-check/3"),
            ):
                expected = (
                    installation.manifest_ref
                    if schema == installation.manifest.schema_version
                    else (
                        route
                        if schema == "model-binding/1"
                        else (
                            binding.engine_config_ref
                            if schema == engine.schema_version
                            else s.software_ref
                        )
                    )
                )
                from lab_generate_skill.domain.evidence import EvidenceMetadata

                metadata = EvidenceMetadata.model_validate(
                    expected.model_dump(
                        include={
                            "media_type",
                            "content_schema",
                            "visibility",
                            "producer",
                        }
                    )
                )
                if store.put(body, metadata, control=control) != expected:
                    raise OwnershipConflict(
                        "Category frozen runtime input changed original reference"
                    )
            accounting_ref = put(accounting, "original-slurm-accounting/1")
            journal = FileResourceJournal(output / "resources", owner, controls, store)
            source_owner = OriginalSourceQualificationOwner(
                source_scope, execution, controller, store
            )
            source_reads = ClosedSourceReadTransport(storage, store, managed.admission)
            verified_source = None
            if retained_source is not None:
                facts["phase"] = "retained_source_validation"
                before = time.monotonic()
                if s.stage_budgets is not None:
                    controls.require_execution_budget(
                        operation,
                        preparation_seconds=s.stage_budgets.assets_seconds
                        + s.source_metadata_seconds
                        + s.setup_seconds,
                        task_seconds=s.task_seconds,
                    )
                with execution_stage(
                    controls, "source", operation, seconds=s.source_metadata_seconds
                ):
                    verified_source = consume_category_navigation_source(
                        source_owner,
                        retained_source,
                        raw,
                        native_ref,
                        public,
                        operation,
                        controls,
                        source_reads,
                    )
                facts.update(
                    source_qualified=True,
                    retained_source_read_seconds=time.monotonic() - before,
                    closed_source_context_ref=verified_source.material.context_ref.model_dump(
                        mode="json"
                    ),
                )
            runner = SlurmCommandRunner()
            probe = AccountingSlurmProbe(
                store,
                controls,
                clock,
                runner,
                sacct=Path("/usr/bin/sacct"),
                squeue=Path("/usr/bin/squeue"),
            )
            verifier = SlurmAllocationVerifier(
                store,
                controls,
                clock,
                probe,
                runner,
                scontrol=Path("/usr/bin/scontrol"),
                nvidia_smi=Path("/usr/bin/nvidia-smi"),
            )
            allocation = verifier.observe(
                execution,
                controller.writer,
                operation.model_copy(
                    update={"operation_id": "category.actor.allocation"}
                ),
            )
            root = Path(
                tempfile.mkdtemp(
                    prefix="shopping18-model-" + execution.job_id + "-", dir="/tmp"
                )
            )
            facts["staged_model_root"] = str(root)
            put(
                json.dumps(
                    {
                        "node_root": str(root),
                        "artifact": models[0].model_dump(mode="json"),
                    },
                    sort_keys=True,
                ).encode(),
                "category-model-staging-plan/1",
            )
            before = time.monotonic()
            with execution_stage(controls, "assets", operation):
                for file in models[0].files:
                    (root / file.path).parent.mkdir(parents=True, exist_ok=True)
                    copy_pinned_file(Path(models[0].root), root, file, control)
                for path in sorted(
                    (p for p in root.rglob("*") if p.is_dir()),
                    key=lambda p: len(p.parts),
                    reverse=True,
                ):
                    path.chmod(0o555)
                root.chmod(0o555)
                artifact = ReleaseArtifact.model_validate(
                    models[0].model_copy(update={"root": str(root)})
                )
            facts["model_staging_seconds"] = time.monotonic() - before
            recovery = RecoveryPlan(
                recovery_id="category.actor.close",
                owner=owner,
                baseline_ref=binding.engine_config_ref,
                restore_component_id="actor-close",
                restore_component_version="1",
                state_coverage=("worker",),
            )
            token = AllocationToken(
                allocation_id="actor.model",
                owner=owner,
                scope="batch",
                resource_kind="actor",
                expected_resource_id="actor.original",
                provider_id="fixed-actor-worker",
                provider_version="1",
                recovery_ref=put(
                    recovery.model_dump_json().encode(), recovery.schema_version
                ),
            )
            model = ActorResourceSpec(
                token=token,
                release_ref=installation.manifest_ref,
                model_binding_ref=route,
                python_executable=installation.python_executable,
                slurm=ActorSlurmBinding(
                    allocation=allocation,
                    srun_executable="/usr/bin/srun",
                    scontrol_executable="/usr/bin/scontrol",
                ),
                artifact=artifact,
                engine_config=engine,
            )
            model_operation = operation.model_copy(
                update={
                    "operation_id": "category.actor.acquire",
                    "allocation_id": token.allocation_id,
                    "recovery_ref": token.recovery_ref,
                }
            )
            source_node = (
                Path(
                    tempfile.mkdtemp(
                        prefix="shopping18-source-" + execution.job_id + "-", dir="/tmp"
                    )
                )
                / "instance"
            )
            candidate_node = (
                Path(
                    tempfile.mkdtemp(
                        prefix="shopping18-execute-" + execution.job_id + "-",
                        dir="/tmp",
                    )
                )
                / "instance"
            )
            facts.update(
                source_node_root=str(source_node),
                candidate_node_root=str(candidate_node),
                phase="runtime_supplied_no_site_or_actor_started",
            )
            runtime = CategoryNavigationProductionRuntime(
                source_owner,
                scope,
                operation,
                model,
                model_operation,
                binding,
                parameters,
                s.software_ref,
                s.software,
                s.template,
                s.browser_assets,
                source_reads,
                journal,
                controls,
                clock,
                verifier,
                output,
                Path(installation.workspace_root),
                source_node,
                candidate_node,
                claim_root,
                claim_scope,
                s.origin,
                accounting_ref,
                s.image,
                s.image_source,
                s.site_seconds,
                s.task_seconds,
                s.setup_seconds,
                s.source_metadata_seconds,
                s.metadata_cleanup_seconds,
                s.physical_close_seconds,
                s.generation_seconds,
                s.interaction_seconds,
                s.actor_cleanup_seconds,
                s.recovery_budgets,
                retained_source,
                verified_source,
                source_installation=installation,
                generation_budgets=s.generation_budgets,
                source_inputs=source_inputs,
            )
            yield SuppliedCategoryNavigationRuntime(runtime, facts, cancellation)
        except BaseException as error:
            primary = error
            if isinstance(error, CategoryNavigationSourceUnconfirmed):
                facts["source_prefix_reuse"] = dict(error.progress.input_reuse)
            facts["error"] = describe_error(error).model_dump(mode="json")
            raise
        finally:
            facts["execution_stage_observations"] = list(controls.stage_observations)
            finish_member_metadata(
                output,
                facts,
                managed.admission.stop_new_io if managed is not None else None,
                primary,
            )

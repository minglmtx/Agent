"""Selected live browser declarations on the existing registered browser interface."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.browser_worker import BrowserWorkerConfiguration
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from lab_generate_skill.domain.lifecycle import AllocationToken, OperationContext
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.map_navigation_browser_initialization import (
    MapNavigationInitialization,
)
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from lab_generate_skill.domain.map_browser_inputs import MapBrowserInputs
from lab_generate_skill.domain.map_browser_collection import MapBrowserCollectionSpec
from lab_generate_skill.domain.map_private_artifact import MapPrivateArtifactPlan
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.site_resource import SiteResourceStarted
from map_preparation_native import MapPreparation
from test_resource_journal import context


def declarations(
    native: MapPreparation,
    site: SiteResourceStarted,
    publication: PreparedPublication,
    session: BrowserSessionSpec,
    base: BrowserWorkerConfiguration,
    root: Path,
    token: AllocationToken,
    *,
    started_ref: EvidenceRef | None = None,
) -> tuple[BrowserWorkerConfiguration, OperationContext]:
    cfg = native.c.spec.configuration
    inputs = cfg.map_inputs
    if (
        inputs is None
        or site.instance.files != cfg.files
        or session.scope != inputs.scope
        or token.owner != inputs.scope.owner
        or token.attempt_id != inputs.scope.attempt_id
        or len(site.instance.ports) != 6
    ):
        raise ValueError("Original Map prepared source/browser allocation required")
    operation = context(token, "acquire").model_copy(
        update={
            "deadline": min(
                datetime.now(timezone.utc) + timedelta(seconds=180),
                native.c.op.deadline,
            ),
            "cancellation_ref": native.c.op.cancellation_ref,
        }
    )
    if isinstance(native.overlay_spec, NavigationSpec):
        value = BrowserWorkerConfiguration.model_validate(
            {
                **base.model_dump(),
                "spec": session,
                "initialization": MapNavigationInitialization(
                    endpoint=site.instance.endpoint,
                    prepared_ref=publication.prepared_ref,
                    site_ref=native.put(site) if started_ref is None else started_ref,
                    native_contract_sha256=native.native_contract_ref.sha256,
                ),
                "map_inputs": None,
            }
        )
        return value, operation
    if native.inputs.original_sources is None:
        raise ValueError(
            "MapData requires its original complete frontend source declaration"
        )
    lifetime = context(token, "map-collection-lifetime").model_copy(
        update={
            "deadline": native.c.op.deadline,
            "cancellation_ref": native.c.op.cancellation_ref,
            "parent_operation_id": native.c.op.operation_id,
        }
    )
    plan = MapPrivateArtifactPlan(
        scope=inputs.scope,
        token=token,
        producer="browser_process",
        workspace_root=cfg.files.workspace_root,
        private_root=str(root / "complete-files"),
        artifact_id="selected-map-browser-files",
        max_files=4096,
        max_file_bytes=512 * 1024**2,
        max_total_bytes=4 * 1024**3,
    )
    collection = MapBrowserCollectionSpec(
        operation=operation,
        lifetime_operation=lifetime,
        original_sources=native.inputs.original_sources,
        tile_origin=f"http://127.0.0.1:{site.instance.ports[5]}",
        max_requests=256,
    )
    value = BrowserWorkerConfiguration.model_validate(
        {
            **base.model_dump(),
            "spec": session,
            "initialization": MapNativeInitialization(
                endpoint=site.instance.endpoint,
                prepared_ref=publication.prepared_ref,
                site_ref=native.put(site) if started_ref is None else started_ref,
            ),
            "map_inputs": MapBrowserInputs(
                plan=plan,
                collection=collection,
                evidence_root=inputs.evidence_root,
                resource_journal_root=str(root / "journal"),
            ),
        }
    )
    return value, operation

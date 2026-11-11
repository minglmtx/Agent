"""Actual selected workspace inputs; no migration, staging, service or Actor effect."""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.adapters.map_runtime.metadata import read_pinned_bytes
from lab_generate_skill.bootstrap.map_native_overlay import load_overlay_inputs
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.lifecycle import (
    ResourceOwner,
    RecoveryPlan,
    AllocationToken,
)
from lab_generate_skill.domain.map_runtime_inputs import MapRuntimeInputs
from lab_generate_skill.bootstrap.map_task_configuration import map_task_configuration
from lab_generate_skill.domain.map_origin import MapOriginPolicy
from lab_generate_skill.domain.release import ReleaseFile, ReleaseArtifact
from lab_generate_skill.domain.release_installation import ReleaseInstallation
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.map.tasks.overlay_spec import (
    SOURCE,
    GOAL,
    START,
    NativeOverlaySpec,
)
from lab_generate_skill.sites.map.tasks.overlay_policy import overlay_initial_spec
from lab_generate_skill.sites.map.frontend_sources import PINS
from lab_generate_skill.sites.map.tasks.overlay_reference_policy import PROOF_SHA
from map_navigation_source_selection import MapNavigationSourceSelection
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from lab_generate_skill.sites.map.tasks.navigation_policy import navigation_initial_spec

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
RUNTIME_PATH = (
    W
    / "experiments/framework-map-intake-20261029-v1/runtime-review-4849553/runtime-inputs.json"
)
RUNTIME_PIN = ReleaseFile(
    path="runtime-inputs.json",
    sha256="53895b2e71f7d41367120e4342179b84def8f9dbf6aa78a65ff8b075761fb0f8",
    size_bytes=4786,
    executable=False,
)
CONTRACT_PATH = (
    W
    / "experiments/sft-map-original-layer-v1/prepared/contracts/b9101b71aacd51b61f6e.json"
)
CONTRACT_PIN = ReleaseFile(
    path=SOURCE + ".json",
    sha256="50356bbd0811eaac447f9bbef29a348a552dc38c2478a1cbec13464f1719cb2d",
    size_bytes=1711,
    executable=False,
)
SOURCE_SIZES = {
    "app/assets/javascripts/index.js": 10812,
    "app/assets/javascripts/leaflet.layers.js": 4667,
    "app/assets/javascripts/leaflet.share.js": 11102,
    "vendor/assets/leaflet/leaflet.osm.js": 8065,
}


def identity() -> TaskIdentity:
    return TaskIdentity(
        site="map",
        family="native_route_map_data",
        contract_version=1,
        split="train",
        task_id=SOURCE,
        source_task_id=SOURCE,
    )


def public_task(endpoint: str, actions: tuple[str, ...]) -> PublicTask:
    from urllib.parse import urlsplit

    if type(endpoint) is not str:
        raise TypeError("Original allocated Map endpoint must be text")
    value = urlsplit(endpoint)
    if (
        endpoint != f"http://127.0.0.1:{value.port}/"
        or value.port is None
        or not 1024 <= value.port <= 65535
    ):
        raise ValueError("Original allocated Map root endpoint required")
    return PublicTask(
        identity=identity(),
        goal=GOAL,
        start_url=endpoint.rstrip("/") + START,
        allowed_actions=actions,
    )


def selected_task(selection: MapNavigationSourceSelection | None) -> TaskIdentity:
    if selection is not None and not isinstance(
        selection, MapNavigationSourceSelection
    ):
        raise TypeError("Explicit validated selected8 navigation source required")
    return identity() if selection is None else selection.public_template.identity


def check_source_scope(
    owner: ResourceOwner,
    scope: StateScope,
    selection: MapNavigationSourceSelection | None,
) -> StateScope:
    owner = ResourceOwner.model_validate(owner)
    task = selected_task(selection)
    if not isinstance(scope, StateScope):
        raise TypeError("Original explicit Map attempt scope required")
    scope = StateScope.model_validate(scope)
    if scope.owner != owner or scope.task != task:
        raise ValueError("Map source scope changed original owner/task")
    return scope


def engineering_scope(
    owner: ResourceOwner, selection: MapNavigationSourceSelection | None
) -> StateScope:
    """Explicit old engineering identity, never a construction default."""
    task = selected_task(selection)
    return StateScope(
        owner=owner,
        task=task,
        attempt_id=(
            "native-map-attempt"
            if selection is None
            else "native-nav-" + task.source_task_id + "-attempt"
        ),
        context_id=(
            "native-map-context"
            if selection is None
            else "native-nav-" + task.source_task_id + "-context"
        ),
    )


@dataclass(frozen=True)
class MapSourceInputs:
    configuration: SiteWorkerConfiguration
    private: NativeOverlaySpec | NavigationSpec
    original_sources: ReleaseArtifact | None
    state_spec_ref: EvidenceRef
    original_reference_ref: EvidenceRef | None
    selection: MapNavigationSourceSelection | None = None

    def public_at(self, endpoint: str, actions: tuple[str, ...]) -> PublicTask:
        if isinstance(self.private, NavigationSpec):
            if self.selection is None:
                raise ValueError("Explicit selected navigation source required")
            return self.selection.public_at(endpoint, actions)
        if self.selection is not None:
            raise ValueError("MapData cannot consume a navigation selection")
        return public_task(endpoint, actions)


def source_inputs(
    store: EvidenceStore,
    owner: ResourceOwner,
    installation: ReleaseInstallation,
    root: Path,
    parent: Path,
    control: OperationControl,
    *,
    scope: StateScope,
    evidence_root: Path,
    selection: MapNavigationSourceSelection | None = None,
) -> MapSourceInputs:
    owner = ResourceOwner.model_validate(owner)
    installation = ReleaseInstallation.model_validate(installation)
    control.checkpoint()
    scope = check_source_scope(owner, scope, selection)
    if not all(isinstance(v, Path) for v in (root, parent, evidence_root)):
        raise TypeError("Original explicit Map input paths required")
    if (
        evidence_root.resolve() != evidence_root
        or not evidence_root.is_relative_to(W)
        or evidence_root == W
    ):
        raise ValueError("Original shared evidence root must remain inside workspace")
    if (
        root.resolve() != root
        or not root.is_relative_to(W)
        or root == W
        or parent.resolve() != parent
        or not parent.is_relative_to("/tmp")
        or parent == Path("/tmp")
    ):
        raise ValueError(
            "Original isolated workspace controls and new private node parent required"
        )
    original = MapRuntimeInputs.model_validate_json(
        read_pinned_bytes(RUNTIME_PATH, RUNTIME_PIN, control)
    )
    private: NativeOverlaySpec | NavigationSpec
    proof_ref: EvidenceRef | None
    if selection is None:
        raw = read_pinned_bytes(CONTRACT_PATH, CONTRACT_PIN, control)
        ref = store.put(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema="map-native-contract/1",
                visibility="private",
                producer="map-selected-engineering-inputs",
            ),
            control=control,
        )
        private = NativeOverlaySpec(task=identity(), native_contract_ref=ref)
        proof = read_pinned_bytes(
            W
            / "archives/legacy-project-reference-library-20261026-v1/records"
            / PROOF_SHA
            / (identity().source_task_id + ".json"),
            ReleaseFile(
                path=identity().source_task_id + ".json",
                sha256=PROOF_SHA,
                size_bytes=177301,
                executable=False,
            ),
            control,
        )
        proof_ref = store.put(
            proof,
            EvidenceMetadata(
                media_type="application/json",
                content_schema="map-native-layer-proof/1",
                visibility="private",
                producer="map-selected-engineering-inputs",
            ),
            control=control,
        )
        # Validate original meaning before any native dispatch; real allocated URL is
        # rebound only after original site start. This validation grants no permission.
        load_overlay_inputs(
            raw,
            ref,
            public_task("http://127.0.0.1:1024/", ("click", "send_msg_to_user")),
        )
    else:
        raw = selection.native
        ref = store.put(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema="map-native-contract/1",
                visibility="private",
                producer="map-selected-engineering-inputs",
            ),
            control=control,
        )
        private = selection.load(
            ref, selection.public_at("http://127.0.0.1:1024/", None)
        )
        proof_ref = None
    task = private.task
    files = original.files.model_copy(
        update={
            "instance_id": (
                "selected-map-" + owner.job_id
                if selection is None
                else "selected-map-nav-" + task.source_task_id[:10] + "-" + owner.job_id
            ),
            "node_root": str(parent / "instance"),
        }
    )
    runtime = MapRuntimeInputs.model_validate(
        original.model_copy(update={"files": files})
    )
    baseline = (
        overlay_initial_spec(task)
        if selection is None
        else navigation_initial_spec(task, private.native_contract_ref.sha256)
    )

    def put(value: object, schema: str) -> EvidenceRef:
        from lab_generate_skill.domain.validation import Contract

        assert isinstance(value, Contract)
        return store.put(
            value.model_dump_json().encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema=schema,
                visibility="private",
                producer="map-selected-engineering-inputs",
            ),
            control=control,
        )

    baseline_ref = put(baseline, "initial-state-spec/1")
    recovery = RecoveryPlan(
        recovery_id="selected-map-environment",
        owner=owner,
        baseline_ref=baseline_ref,
        restore_component_id="map-services",
        restore_component_version="1",
        state_coverage=baseline.environment_reset_checks,
    )
    token = AllocationToken(
        allocation_id="site-allocation",
        owner=owner,
        scope="batch",
        resource_kind="site",
        expected_resource_id=files.instance_id,
        provider_id="fixed-site-worker",
        provider_version="6",
        recovery_ref=put(recovery, "recovery-plan/1"),
    )
    cfg = map_task_configuration(
        runtime,
        private,
        scope,
        token,
        installation,
        origin=(
            MapOriginPolicy.dynamic() if isinstance(private, NavigationSpec) else None
        ),
        evidence_root=evidence_root,
        resource_journal_root=root / "journal",
        artifact_root=root / "map-native-files",
        max_files=1024,
        max_file_bytes=512 * 1024**2,
        max_total_bytes=4 * 1024**3,
    )
    sources: ReleaseArtifact | None = None
    if selection is None:
        frontend = next(t for t in runtime.trees if t.role == "frontend")
        sources = ReleaseArtifact(
            artifact_id="selected-map-original-frontend",
            root=frontend.source_root,
            files=tuple(
                ReleaseFile(
                    path=name,
                    sha256=PINS[name],
                    size_bytes=SOURCE_SIZES[name],
                    executable=False,
                )
                for name in sorted(SOURCE_SIZES)
            ),
        )
    control.checkpoint()
    return MapSourceInputs(cfg, private, sources, baseline_ref, proof_ref, selection)

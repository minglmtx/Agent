"""Rebuild existing preparation records with closed-source, read-only authority."""

from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.bootstrap.map_native_overlay import load_overlay_inputs
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.ports.lifecycle import OperationControl, OperationControls
from lab_generate_skill.ports.map_state_artifacts import MapStateFileReader
from lab_generate_skill.sites.map.tasks.overlay_preparation_checks import (
    OverlayPreparationChecks,
)
from lab_generate_skill.sites.map.tasks.overlay_spec import NativeOverlaySpec
from lab_generate_skill.sites.map.tasks.overlay_policy import overlay_initial_spec
from lab_generate_skill.sites.map.tasks.navigation_spec import NavigationSpec
from lab_generate_skill.sites.map.tasks.navigation_input import bind_navigation_inputs
from lab_generate_skill.sites.map.tasks.navigation_policy import navigation_initial_spec
from lab_generate_skill.sites.map.tasks.navigation_preparation_checks import (
    NavigationPreparationChecks,
)
from lab_generate_skill.sites.map.tasks.state_codec import MapTaskStateCodec
from lab_generate_skill.sites.map.state_rules import object_json
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.adapters.map_artifacts.closed_access import (
    ClosedMapSourceAccess,
)


class ClosedPreparationAuthority:
    def __init__(
        self,
        initial: BaselineInputs,
        access: ClosedMapSourceAccess,
        store: EvidenceStore,
    ) -> None:
        self.initial, self.access, self.store = initial, access, store

    def verify_binding(
        self,
        binding: TaskBinding,
        public_task: PublicTask,
        private_spec: bytes,
        baseline: bytes,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        old = self.initial
        if (
            op.mode != "cleanup"
            or binding != old.binding
            or public_task != old.public_task
            or baseline != old.spec.model_dump_json().encode()
            or private_spec != self.store.read(binding.private_spec_ref, control)
            or old.prepared.scope != self.access.browser.configuration.spec.scope
        ):
            raise OwnershipConflict(
                "Closed Map preparation changed original read-only binding"
            )
        private = MapTaskStateCodec(binding.identity).private_type.model_validate_json(
            private_spec
        )
        raw = self.store.read(private.native_contract_ref, control)
        original: NativeOverlaySpec | NavigationSpec
        if isinstance(private, NavigationSpec):
            original = bind_navigation_inputs(
                object_json(raw),
                private.native_contract_ref,
                public_task,
                private.binding,
            ).private_spec
            expected = navigation_initial_spec(
                binding.identity, private.native_contract_ref.sha256
            )
        else:
            original = load_overlay_inputs(
                raw, private.native_contract_ref, public_task
            ).private_spec
            expected = overlay_initial_spec(binding.identity)
        if original != private or old.spec != expected:
            raise OwnershipConflict("Closed Map preparation changed native meaning")

    def verify(
        self,
        inputs: PreparationInputs,
        checks: StateChecks,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        old = self.initial
        inputs.request.check_site(self.access.site.configuration)
        if (
            op.mode != "cleanup"
            or inputs.binding != old.binding
            or inputs.public_task != old.public_task
            or inputs.spec != old.spec
            or inputs.environment != old.environment
            or inputs.request.operation != old.preparation.operation
            or checks != old.preparation.checks
        ):
            raise OwnershipConflict(
                "Closed Map preparation changed original facts/checks"
            )
        control.checkpoint()


def closed_map_preparations(
    initial: BaselineInputs,
    access: ClosedMapSourceAccess,
    files: MapStateFileReader,
    store: EvidenceStore,
    controls: OperationControls,
) -> EvidencePreparationRecords:
    authority = ClosedPreparationAuthority(initial, access, store)
    return EvidencePreparationRecords(
        store,
        controls,
        EvidenceTaskBindings(store, controls, authority),
        (
            NavigationPreparationChecks(store, files)
            if initial.binding.identity.family == "navigation_page_identity"
            else OverlayPreparationChecks(store, files)
        ),
        authority,
    )

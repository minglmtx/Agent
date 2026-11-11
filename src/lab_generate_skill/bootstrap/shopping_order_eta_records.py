"""Fixed source recomputation plus mandatory actual TaskBinding authority."""

from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.bootstrap.shopping_order_eta import load_order_eta_inputs
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.task_bindings import TaskBindingAuthority, TaskBindings
from lab_generate_skill.sites.shopping.tasks.order_eta_binding import (
    OrderEtaBindingAuthority,
)


def bind_order_eta_records(
    store: EvidenceStore, controls: OperationControls, authority: TaskBindingAuthority
) -> TaskBindings:
    return EvidenceTaskBindings(
        store,
        controls,
        OrderEtaBindingAuthority(store, load_order_eta_inputs, authority),
    )

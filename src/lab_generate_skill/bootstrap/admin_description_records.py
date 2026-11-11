"""Wire the current description verifier and required real task authority."""

from lab_generate_skill.adapters.storage.task_bindings import EvidenceTaskBindings
from lab_generate_skill.bootstrap.admin_description import (
    load_product_description_inputs,
)
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls
from lab_generate_skill.ports.task_bindings import TaskBindingAuthority, TaskBindings
from lab_generate_skill.sites.shopping_admin.tasks.product_description_binding import (
    ProductDescriptionBindingAuthority,
)


def bind_product_description_records(
    store: EvidenceStore, controls: OperationControls, authority: TaskBindingAuthority
) -> TaskBindings:
    site = ProductDescriptionBindingAuthority(
        store, load_product_description_inputs, authority
    )
    return EvidenceTaskBindings(store, controls, site)

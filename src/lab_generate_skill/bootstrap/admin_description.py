"""Assemble bounded native decoding with the selected site's pure task binding.

PublicTask is explicit caller-approved input, not generated from private fields.
This entry does not read files, activate a task or grant execution permission.
"""

from lab_generate_skill.adapters.plans.admin_native_input import decode_admin_native
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.shopping_admin.tasks.product_description_input import (
    bind_product_description_inputs,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_description_spec import (
    ProductDescriptionInputs,
)


def load_product_description_inputs(
    raw: bytes,
    reference: EvidenceRef,
    public_task: PublicTask,
) -> ProductDescriptionInputs:
    reference = EvidenceRef.model_validate(reference)
    public_task = PublicTask.model_validate(public_task)
    try:
        native = decode_admin_native(raw, reference)
        return bind_product_description_inputs(native, reference, public_task)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise EvidenceIntegrityError(
            "Invalid original product-description input"
        ) from error

"""Bounded native category bytes into existing pure Shopping data codecs."""

from lab_generate_skill.adapters.plans.native_input import decode_native_object
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.shopping.tasks.navigation_input import (
    bind_category_navigation_inputs,
)
from lab_generate_skill.sites.shopping.tasks.navigation_spec import (
    CategoryNavigationInputs,
)


def load_category_navigation_inputs(
    raw: bytes, reference: EvidenceRef, public: PublicTask
) -> CategoryNavigationInputs:
    try:
        native = decode_native_object(
            raw, reference, content_schema="shopping-native-contract/1"
        )
        return bind_category_navigation_inputs(native, reference, public)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise EvidenceIntegrityError(
            "Invalid original category navigation input"
        ) from error

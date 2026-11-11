"""Exact private native bytes and an explicit source binding; no admission grant."""

from lab_generate_skill.adapters.plans.native_input import decode_native_object
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.map.tasks.navigation_input import bind_navigation_inputs
from lab_generate_skill.sites.map.tasks.navigation_spec import (
    NavigationInputs,
    NavigationSourceBinding,
)


def load_navigation_inputs(
    raw: bytes,
    reference: EvidenceRef,
    public: PublicTask,
    *,
    binding: NavigationSourceBinding,
) -> NavigationInputs:
    try:
        native = decode_native_object(
            raw, reference, content_schema="map-native-contract/1"
        )
        return bind_navigation_inputs(native, reference, public, binding)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise EvidenceIntegrityError("Invalid original Map navigation input") from error

"""Bounded private Map contract bytes through the common input boundary."""

from lab_generate_skill.adapters.plans.native_input import decode_native_object
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.map.tasks.overlay_input import bind_overlay_inputs
from lab_generate_skill.sites.map.tasks.overlay_spec import NativeOverlayInputs


def load_overlay_inputs(
    raw: bytes, reference: EvidenceRef, public: PublicTask
) -> NativeOverlayInputs:
    try:
        native = decode_native_object(
            raw, reference, content_schema="map-native-contract/1"
        )
        return bind_overlay_inputs(native, reference, public)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise EvidenceIntegrityError(
            "Invalid original Map route/overlay input"
        ) from error

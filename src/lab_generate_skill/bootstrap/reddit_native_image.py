"""Bounded original bytes through current private input reader; no legacy runner."""

from lab_generate_skill.adapters.plans.native_input import decode_native_object
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.reddit.tasks.image_input import bind_image_inputs
from lab_generate_skill.sites.reddit.tasks.image_spec import NativeImageInputs


def load_image_inputs(
    raw: bytes, reference: EvidenceRef, public: PublicTask
) -> NativeImageInputs:
    try:
        native = decode_native_object(
            raw, reference, content_schema="reddit-native-contract/1"
        )
        return bind_image_inputs(native, reference, public)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise EvidenceIntegrityError(
            "Invalid original Reddit native-image input"
        ) from error

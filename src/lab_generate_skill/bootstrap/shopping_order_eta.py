"""Bind bounded original bytes to an explicit caller-approved public ETA task."""

from lab_generate_skill.adapters.plans.native_input import decode_native_object
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.shopping.tasks.order_eta_input import (
    bind_order_eta_inputs,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_spec import OrderEtaInputs


def load_order_eta_inputs(
    raw: bytes, reference: EvidenceRef, public_task: PublicTask
) -> OrderEtaInputs:
    try:
        native = decode_native_object(
            raw, reference, content_schema="shopping-native-contract/1"
        )
        return bind_order_eta_inputs(native, reference, public_task)
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise EvidenceIntegrityError("Invalid original Shopping ETA input") from error

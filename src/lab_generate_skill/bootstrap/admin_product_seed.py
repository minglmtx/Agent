"""Bind actual private fixture bytes to the selected site's strict seed contract."""

import hashlib
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.adapters.processes.wire_json import json_object
from lab_generate_skill.sites.shopping_admin.tasks.product_seed_contract import (
    ProductSeed,
    ProductSeedScenario,
)


def load_admin_product_seed(raw: bytes, reference: EvidenceRef) -> ProductSeed:
    reference = EvidenceRef.model_validate(reference)
    if (
        type(raw) is not bytes
        or not 1 <= len(raw) <= 64 * 1024
        or reference.size_bytes != len(raw)
        or reference.sha256 != hashlib.sha256(raw).hexdigest()
    ):
        raise EvidenceIntegrityError(
            "Product fixture differs from bounded original bytes"
        )
    json_object(raw)  # reject duplicates/nonfinite tokens before typed decoding
    return ProductSeed(
        reference=reference, scenario=ProductSeedScenario.model_validate_json(raw)
    )

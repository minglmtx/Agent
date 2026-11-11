"""Synthetic kernel closure proof for software review; never native acceptance."""

import json
from typing import Any
import pytest
from lab_generate_skill.domain.evidence import EvidenceMetadata


def closed_proof(module: Any, patch: pytest.MonkeyPatch) -> None:
    original = module.observe_closed

    def close(*args: Any, **kwargs: Any) -> Any:
        value = original(*args, **kwargs)
        if value is None:
            return None
        store, control = args[3], args[4]
        raw = dict(
            engineering_only=True,
            synthetic_kernel=True,
            phase="closed",
            target=value.target.model_dump(mode="json"),
            kernel=[dict(synthetic=True)],
            commands=[dict(synthetic=True, complete=True, returncode=0)],
            error=None,
        )
        ref = store.put(
            json.dumps(raw).encode(),
            EvidenceMetadata(
                media_type="application/json",
                content_schema="synthetic-closure-proof/1",
                visibility="private",
                producer="unit",
            ),
            control=control,
        )
        return value.model_copy(update={"evidence": ref})

    patch.setattr(module, "observe_closed", close)

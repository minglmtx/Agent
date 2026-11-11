"""Pure original category binding; review paths are labels, never runtime rights."""

import json
from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from .navigation_spec import (
    CategoryNavigationInputs,
    CategoryNavigationSpec,
    OriginalCategoryNavigation,
)


def bind_category_navigation_inputs(
    native: dict[str, Any], reference: EvidenceRef, public: PublicTask
) -> CategoryNavigationInputs:
    if type(native) is not dict:
        raise TypeError("Original category navigation object required")
    for name in ("heldout_quarantine", "eligible_for_training", "task_text_changed"):
        if type(native.get(name)) is not bool:
            raise ValueError("Original category scope flag type changed")
    if type(native.get("api_calls")) is not int:
        raise ValueError("Original category API count must be an integer")
    original = OriginalCategoryNavigation.model_validate_json(
        json.dumps(native, allow_nan=False)
    )
    public = PublicTask.model_validate(public)
    actual, expected = urlsplit(public.start_url), urlsplit(original.start_path)
    if (
        public.goal != original.goal
        or actual.scheme not in ("http", "https")
        or not actual.netloc
        or actual.username is not None
        or actual.password is not None
        or (actual.path, actual.query, actual.fragment)
        != (expected.path, expected.query, expected.fragment)
    ):
        raise ValueError("Explicit public category goal and exact start path required")
    return CategoryNavigationInputs(
        public_task=public,
        private_spec=CategoryNavigationSpec(
            task=public.identity,
            native_contract_ref=reference,
            original=original,
        ),
    )

"""Current package joins bounded original decoder and fixed collector selector."""

import json
from typing import Any
import pytest
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.bootstrap.admin_navigation import load_admin_navigation_inputs
from lab_generate_skill.bootstrap.browser_capture import browser_collector
from lab_generate_skill.sites.shopping_admin.navigation_page_capture import (
    AdminNavigationPageCollector,
)
from browser_worker_fixtures import configuration
from test_admin_navigation_input import contracts as contracts


def test_all_selected_original_bytes_reach_current_bootstrap(contracts: Any) -> None:
    from test_admin_navigation_input import SCOPE, GROUP
    from pathlib import Path

    selected = [
        json.loads(line)
        for line in (SCOPE / "tasks.jsonl").read_text().splitlines()
        if json.loads(line)["effective_batch_id"] == GROUP
    ]
    for row, (native, reference, public) in zip(selected, contracts, strict=True):
        raw = Path(row["contract_pin_check"]["path"]).read_bytes()
        inputs = load_admin_navigation_inputs(raw, reference, public)
        assert inputs.private_spec.task == public.identity
        assert inputs.private_spec.start_path == native["spec"]["start_path"]
        assert inputs.private_spec.admission == "unverified"
    with pytest.raises(EvidenceIntegrityError, match="bytes differ"):
        load_admin_navigation_inputs(b"{}", contracts[0][1], contracts[0][2])


@pytest.mark.parametrize(
    "field,value",
    [
        ("none", None),
        ("family", "unsupported"),
        ("site", "map"),
        ("contract_version", 2),
        ("split", "test"),
    ],
)
def test_fixed_current_collector_requires_selected_train_contract(
    contracts: Any, field: str, value: Any
) -> None:
    public = contracts[0][2]
    if field != "none":
        public = public.model_copy(
            update={"identity": public.identity.model_copy(update={field: value})}
        )
    base = configuration()
    spec = base.spec.model_copy(
        update={
            "task": public,
            "scope": base.spec.scope.model_copy(update={"task": public.identity}),
        }
    )
    collector = browser_collector(base.model_copy(update={"spec": spec}))
    assert (
        isinstance(collector, AdminNavigationPageCollector)
        if field == "none"
        else collector is None
    )

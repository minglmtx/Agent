"""Original category CAS/native/prepared-browser/unique baseline/full Reset."""

from pathlib import Path
from typing import Any
import pytest
from shopping_prepared_family_fixtures import prepared_family_case
from test_shopping_category_navigation_input import originals as originals
from site_instance_fixtures import node_path as node_path


def test_all18_actual_category_records_prepared_browser_unique_view_and_full_reset(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, originals: Any
) -> None:
    for index, (raw, _, public) in enumerate(originals):
        root = tmp_path / public.identity.source_task_id
        root.mkdir()
        native = node_path / public.identity.source_task_id
        native.mkdir()
        with monkeypatch.context() as patch:
            prepared_family_case(
                root,
                native,
                patch,
                "none",
                category=(raw, public),
                measure_body_reads=index == 0,
            )


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_site",
        "wrong_prepared",
        "missing_task_checks",
        "native_contract",
        "revoked",
        "cancel",
    ],
)
def test_original_dynamic_and_exact_binding_faults_stop_before_browser_and_keep_reset(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    raw, _, public = originals[0]
    prepared_family_case(
        tmp_path, node_path, monkeypatch, fault, category=(raw, public)
    )

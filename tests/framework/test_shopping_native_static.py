"""Exact native asset provenance required by the Shopping seed consumer."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.sites.shopping.native_static import NativeStaticPublication
from lab_generate_skill.sites.shopping.static_program import NATIVE_STATIC
from shopping_services_fixtures import Commands
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "change",
    ["none", "empty", "path", "overlap", "digest", "external", "namespace", "extra"],
)
def test_native_original_publication_normal_and_rejected_inputs(
    tmp_path: Path, change: str
) -> None:
    raw = Commands(tmp_path).run((NATIVE_STATIC,), guard())
    if change == "none":
        parsed = NativeStaticPublication.model_validate_json(raw)
        assert parsed.Magento_OfflinePayments.original_published_sha256 == {
            "old.js": "a" * 64
        }
        return
    data = json.loads(raw)
    row = data["Magento_OfflinePayments"]
    if change == "empty":
        row["added_installed_sha256"] = {}
    elif change == "path":
        row["added_installed_sha256"] = {"../outside": "b" * 64}
    elif change == "overlap":
        row["added_installed_sha256"] = {"old.js": "a" * 64}
    elif change == "digest":
        row["original_published_sha256"] = {"old.js": "bad"}
    elif change == "external":
        row["external_source_used"] = True
    elif change == "namespace":
        row["original_published_namespace"] = "/other"
    else:
        data["Magento_Other"] = row
    with pytest.raises(ValueError):
        NativeStaticPublication.model_validate_json(json.dumps(data))

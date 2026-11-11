"""Exact production PHP counter projection; retained metadata and live HTTP faults."""

import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import pytest
from lab_generate_skill.sites.shopping.tasks.navigation_search_program import (
    SEARCH_CONTENTS,
)
from lab_generate_skill.sites.shopping.tasks.navigation_search_contents import (
    NavigationSearchContents,
)
from shopping_search_inventory_http_fixtures import contents_server
from test_shopping_search_inventory_http import command
from shopping_native_live import IMAGE
from site_instance_fixtures import node_path as node_path
from test_shopping_category_navigation_input import originals as originals

NORMALIZATION = "original-shopping-search-physical-identity-v2"
W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
C = W / "experiments/framework-combined-release-20261030-v1"


def capture(port: int) -> NavigationSearchContents:
    result = subprocess.run(
        command(SEARCH_CONTENTS, str(port), "10"), capture_output=True, timeout=15
    )
    assert result.returncode == 0, result.stderr.decode()
    value = NavigationSearchContents.model_validate_json(result.stdout)
    assert value.normalization == NORMALIZATION
    return value


def test_counter_only_restart_keeps_raw_evidence_and_equal_versioned_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with contents_server() as (state, port):
        original = state.metadata
        counter = [1]

        def metadata() -> dict[str, Any]:
            data = original()
            for row in data["indices"].values():
                row["version"] = counter[0]
                row["primary_terms"] = [counter[0]]
            return data

        monkeypatch.setattr(state, "metadata", metadata)
        before = capture(port)
        counter[0] = 2
        after = capture(port)
        assert before.raw_metadata_sha256 != after.raw_metadata_sha256
        assert before.metadata_sha256 == after.metadata_sha256
        assert before.content_sha256 == after.content_sha256
        assert before.indices == after.indices and before.documents == 2
        assert state.stats_reads == state.alias_reads == 4
        assert sorted(state.deleted) == sorted(state.names * 2)


@pytest.mark.parametrize(
    "field",
    [
        "mappings",
        "settings",
        "mapping_version",
        "settings_version",
        "aliases_version",
        "unrecognized_metadata",
    ],
)
def test_semantic_and_unknown_metadata_remain_visible_across_measurements(
    field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with contents_server() as (state, port):
        original = state.metadata
        changed = [False]

        def metadata() -> dict[str, Any]:
            data = original()
            if changed[0]:
                for row in data["indices"].values():
                    if field == "mappings":
                        row[field] = {"properties": {"x": {"type": "keyword"}}}
                    elif field == "settings":
                        row[field]["index"]["refresh_interval"] = "30s"
                    else:
                        row[field] = 2
            return data

        monkeypatch.setattr(state, "metadata", metadata)
        before = capture(port)
        changed[0] = True
        after = capture(port)
        assert before.metadata_sha256 != after.metadata_sha256
        assert before.content_sha256 != after.content_sha256


def test_counter_mutation_during_one_measurement_still_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with contents_server() as (state, port):
        original = state.metadata
        reads = [0]

        def metadata() -> dict[str, Any]:
            data = original()
            reads[0] += 1
            for row in data["indices"].values():
                row["version"] = reads[0]
            return data

        monkeypatch.setattr(state, "metadata", metadata)
        result = subprocess.run(
            command(SEARCH_CONTENTS, str(port), "10"), capture_output=True, timeout=15
        )
        assert result.returncode == 2 and not result.stdout
        assert b"changed during contents measurement" in result.stderr
        assert sorted(state.deleted) == sorted(state.names)


@pytest.mark.parametrize("version", [None, 0, -1, True, "1", {}, []])
def test_invalid_counter_refuses_before_scroll(
    version: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with contents_server() as (state, port):
        original = state.metadata

        def metadata() -> dict[str, Any]:
            data = original()
            for row in data["indices"].values():
                if version is None:
                    row.pop("version")
                else:
                    row["version"] = version
            return data

        monkeypatch.setattr(state, "metadata", metadata)
        result = subprocess.run(
            command(SEARCH_CONTENTS, str(port), "10"), capture_output=True, timeout=15
        )
        assert result.returncode == 2 and not result.stdout
        assert b"Unsupported original index metadata" in result.stderr
        assert not state.deleted
        assert not any("/_search" in path for _, path in state.calls)


def test_legacy_receipt_keeps_its_original_normalization_and_canonical_bytes() -> None:
    raw = (
        C
        / "shopping-snapshot-contents-native-4961505/shopping_navigation_search_after.json"
    ).read_bytes()
    value = NavigationSearchContents.model_validate_json(raw)
    assert value.normalization == "original-shopping-search-physical-identity-v1"
    assert value.model_dump_json().encode() == raw
    with pytest.raises(ValueError):
        NavigationSearchContents.model_validate(
            {**value.model_dump(), "normalization": "unknown-policy"}
        )


def test_exact_frozen_native_metadata_pair_consumes_production_projection_without_prefix(
    tmp_path: Path,
) -> None:
    # These are engineering diagnostic metadata, not old task/source qualification.
    root = C / "shopping-search-metadata-restart-4962292"
    manifest = json.loads((root / "result.json").read_bytes())
    assert manifest["passed"] and manifest["all_current_services_reaped"]
    values = []
    for name in ["metadata-before", "metadata-after"]:
        pin = manifest["artifacts"][name]
        raw = Path(pin["path"]).read_bytes()
        assert (
            hashlib.sha256(raw).hexdigest() == pin["sha256"]
            and len(raw) == pin["size_bytes"]
        )
        values.append(json.loads(raw))
    pair = [json.loads(v["raw_metadata_canonical"]) for v in values]
    original = copy.deepcopy(pair)
    prefix = SEARCH_CONTENTS.split(" $id=identity();$before=metadata($id);")[0]
    # The exact production functions run; request/identity are never invoked.
    encoded = base64.b64encode(json.dumps(pair).encode()).decode()
    program = (
        prefix
        + "\n$values=json_decode(base64_decode('"
        + encoded
        + "'),false,128,JSON_THROW_ON_ERROR);$answer=[];foreach($values as $v)$answer[]=['raw'=>digest($v),'normalized'=>digest(projected($v))];\n}catch(Throwable $e){fwrite(STDERR,$e->getMessage());exit(2);}echo json_encode($answer,JSON_THROW_ON_ERROR);"
    )
    p = tmp_path / "projection.php"
    p.write_text("<?php\n" + program)
    args = list(command(""))
    index = args.index(str(IMAGE))
    args[index:index] = ["--bind", str(tmp_path) + ":/fixture:ro"]
    args[-2:] = ["/fixture/projection.php", "1234", "10"]
    result = subprocess.run(args, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode()
    rows = json.loads(result.stdout)
    assert [x["raw"] for x in rows] == [v["raw_metadata_sha256"] for v in values]
    assert rows[0]["raw"] != rows[1]["raw"]
    assert rows[0]["normalized"] == rows[1]["normalized"]
    assert pair == original


def test_v2_component_reaches_original_complete_contents_consumer_and_policy_mix_refuses(
    node_path: Path, originals: Any
) -> None:
    # A fresh synthetic worker generates the complete linked fixture. It is never
    # an original task result; only the explicit Search policy field changes.
    from shopping_category_native_fixtures import worker, request
    from lab_generate_skill.sites.shopping.tasks.navigation_recovery import (
        CategoryNavigationRecoverySnapshot,
    )
    from lab_generate_skill.sites.shopping.tasks.navigation_contents import (
        NavigationContents,
    )
    from test_slurm_commands import guard

    raw, _, public = originals[0]
    instance, _ = worker(node_path)
    try:
        result = instance.execute_task(request(raw, public), control=guard(60))
        saved = CategoryNavigationRecoverySnapshot.model_validate_json(
            result.private_result
        )
        assert saved.contents is not None
        body = saved.contents.model_dump()
        body["before"]["search"]["normalization"] = NORMALIZATION
        body["search"]["normalization"] = NORMALIZATION
        body["search"]["raw_metadata_sha256"] = "f" * 64
        accepted = NavigationContents.model_validate(body)
        accepted.require_snapshot(saved.state)
        assert accepted.search.content_sha256 == accepted.before.search.content_sha256
        mixed = copy.deepcopy(body)
        mixed["before"]["search"][
            "normalization"
        ] = "original-shopping-search-physical-identity-v1"
        with pytest.raises(ValueError, match="Contents changed"):
            NavigationContents.model_validate(mixed)
        changed = copy.deepcopy(body)
        changed["search"]["metadata_sha256"] = "e" * 64
        with pytest.raises(ValueError, match="Contents changed"):
            NavigationContents.model_validate(changed)
    finally:
        instance.stop(guard())

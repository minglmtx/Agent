"""Exact selected historical files through new private storage and DB comparison.

No site, HTTP, Actor, DB query or training admission. Original archive is read
only; explicit selected members are published in this job's private workspace.
"""

import hashlib
import json
import os
from pathlib import Path
import tarfile
from typing import Any
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.sites.map.native_compare import compare_database
from map_artifact_fixtures import case
from map_database_original_oracle import oracle
from test_slurm_commands import guard

SOURCE = Path(
    "/home/atuin/r102bf/r102bf10/lmtx/outputs/other-sites-validation-v1/drafts/"
    "map-last-native-single-cold-complement-20261007-v1/cycle-0.tar.gz"
)
SOURCE_SHA = "30b0de68b07d659ee6f32deeabc3d1e1f53da0ff8e0d20fd47ba5d4fa935c218"
INDEX_SHA = "95d0ff1014c96a50c30fc99c02fc6e23d849e74318b73b0cbc17aa8b1c97009b"
PREFIX = "b9101b71aacd51b61f6e/controls/"
MEMBERS = {
    "transport.json": (
        "native-layer-data-transport/native-batch-transport.json",
        39718,
        "2b59e0c444d594fceae8000a722e345c5d14b35c99ac7166c8d4ca1ce3b94240",
    ),
    "database-0.json": (
        "layer-final-0-full-independent-database.json",
        86791226,
        "3e7924e9266094133a5985f51b4621735d3658ee22e9253b99bf6d8c940c7fcb",
    ),
    "database-1.json": (
        "layer-final-1-full-independent-database.json",
        103679486,
        "a79730fce94f7fbf99e64cb20650871ca91d2943e4d9d66233a1f3e58bbfa1b1",
    ),
    "union-0.osm": (
        "native-layer-data-transport/request-0/complete-adapted-map.osm",
        79268555,
        "a48bf6a32d3529e47f5511c8058ba6da4d525d888ae9990e4251bf9e3a3e1567",
    ),
    "union-1.osm": (
        "native-layer-data-transport/request-1/complete-adapted-map.osm",
        98248448,
        "1e139f5a6d2e6fb6dd14eceae697f2af3a79a8e09e6d61b2eec00271fa06eff5",
    ),
}


def selected_index() -> dict[str, Any]:
    raw = SOURCE.with_name("cycle-0.members.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == INDEX_SHA
    index: dict[str, Any] = json.loads(raw)["files"]
    for member, size, digest in MEMBERS.values():
        assert index[PREFIX + member] == {"bytes": size, "sha256": digest}
    return index


def test_historical_file_fixture_preflight(tmp_path: Path) -> None:
    selected_index()
    old = oracle()
    assert callable(old["compare_database_union"])
    writer, _ = case(tmp_path)
    assert sum(v[1] for v in MEMBERS.values()) < writer.plan.max_total_bytes
    assert max(v[1] for v in MEMBERS.values()) < writer.plan.max_file_bytes
    assert writer.state == "new" and not writer.root.exists()


def test_actual_selected_full_files_private_readback_and_original_oracle() -> None:
    selected_index()
    assert SOURCE.stat().st_size == 88841614
    with SOURCE.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == SOURCE_SHA
    directory = Path(os.environ["LAB_JOB_OUTPUT_DIRECTORY"]) / "historical-files"
    directory.mkdir(mode=0o700)
    writer, authority = case(directory)
    writer.initialize(guard())
    # Read just five explicitly pinned members. Never tar.extract/extractall,
    # never import or execute anything from this historical archive.
    with tarfile.open(SOURCE, "r:gz") as archive:
        entries = archive.getmembers()
        for name, (member, size, digest) in MEMBERS.items():
            matches = [item for item in entries if item.name == PREFIX + member]
            assert len(matches) == 1
            item = matches[0]
            assert item.isfile() and item.size == size
            member_stream = archive.extractfile(item)
            assert member_stream is not None
            with member_stream:
                data = member_stream.read(size + 1)
            assert len(data) == size and hashlib.sha256(data).hexdigest() == digest
            pin = writer.retain(name, data, guard(60))
            assert pin.sha256 == digest and pin.size_bytes == size
    handle = writer.seal(guard(120))
    (directory / "handle.json").write_text(handle.model_dump_json())
    reader = MapArtifactReader(writer.plan, directory, authority)
    manifest = reader.manifest(handle, guard(120))
    assert {item.path for item in manifest.artifact.files} == set(MEMBERS)
    transport = json.loads(reader.read(handle, "transport.json", guard(120)))
    assert len(transport["requests"]) == 2
    results = []
    old = oracle()
    for index in (0, 1):
        request = transport["requests"][index]
        bounds = request["requested_bbox_strings"]
        database = json.loads(reader.read(handle, f"database-{index}.json", guard(120)))
        payload = reader.read(handle, f"union-{index}.osm", guard(120))
        current = compare_database(
            payload, bounds, database, response_kind="adapted_union"
        )
        original = old["compare_database_union"](payload, bounds, database)
        result = dict(
            request_index=index, bounds=bounds, current=current, original=original
        )
        results.append(result)
        # Persist diagnostic comparisons before assertions, retaining original
        # disagreements rather than replacing them with a synthesized success.
        (directory / "comparisons.json").write_text(
            json.dumps(results, indent=2) + "\n"
        )
        assert current["checks"] == original["checks"]
        assert current["counts"] == original["counts"]
        assert (
            current["initial_native_bbox_nodes"]
            == original["initial_native_bbox_nodes"]
        )
        assert current["passed"] is original["passed"] is True
        assert not current["provenance_verified"]
    (directory / "result.json").write_text(
        json.dumps(
            dict(
                passed=True,
                archive_sha256=SOURCE_SHA,
                index_sha256=INDEX_SHA,
                selected_members=MEMBERS,
                comparisons=results,
                historical_file_identity_verified=True,
                new_runtime_request_provenance_verified=False,
                production_authority_connected=False,
                actual_map_site_run=False,
                actor_calls=0,
                paid_calls=0,
                task_admitted=False,
            ),
            indent=2,
        )
        + "\n"
    )

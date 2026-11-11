"""Exact source rules, complete served evidence and affected process composition."""

import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
from typing import Any
import pytest
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    InvalidTransition,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.adapters.map_artifacts.reader import MapArtifactReader
from lab_generate_skill.sites.map.native_frontend_source import frontend_source
from lab_generate_skill.sites.map.native_renderer_source import renderer_source
from lab_generate_skill.sites.map.native_served_rules import (
    executable_source,
    reviewed_sources,
    candidate_names,
    RENDERER_READ,
)
from lab_generate_skill.sites.map.native_served_capture import NativeServedCapture
from lab_generate_skill.sites.map.native_process_collector import (
    MapNativeProcessCollector,
)
from map_database_original_oracle import ROOT, CAPSULE
from map_served_fixtures import (
    originals,
    served_case,
    Response,
    ServedPage,
    ORIGIN,
    TILES,
)
from map_route_fixtures import collection, readout
from test_slurm_commands import guard


def test_source_transforms_match_original_capsule_and_literals() -> None:
    raw = CAPSULE.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "3c537fffffcf2768fc3bcedb4e567ed39565f76faf01f3b1f685614d35e724f5"
    )
    pins = json.loads(raw)["members"]

    def selected(rel: str, names: set[str], namespace: dict[str, Any]) -> ast.Module:
        source = (ROOT / rel).read_bytes()
        assert hashlib.sha256(source).hexdigest() == pins[rel]["sha256"]
        tree = ast.parse(source)
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                try:
                    namespace[node.targets[0].id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
            if isinstance(node, ast.FunctionDef) and node.name in names:
                node.body = [
                    item for item in node.body if not isinstance(item, ast.ImportFrom)
                ]
                exec(
                    compile(ast.Module(body=[node], type_ignores=[]), rel, "exec"),
                    namespace,
                )
        return tree

    front: dict[str, Any] = dict(hashlib=hashlib)
    selected(
        "src/lab_generate_skill/map_native_layer_refresh.py", {"patch_source"}, front
    )
    selected(
        "src/lab_generate_skill/map_native_layer_runtime.py", {"frontend_source"}, front
    )
    renderer: dict[str, Any] = dict(hashlib=hashlib)
    selected(
        "src/lab_generate_skill/map_native_renderer_index.py",
        {"patch_source", "require_exact_private_source"},
        renderer,
    )
    served: dict[str, Any] = dict(re=re)
    tree = selected(
        "scripts/map_native_served_refresh.py", {"executable_source"}, served
    )
    original_readers = [
        ast.literal_eval(n.args[0])
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "evaluate"
        and n.args
    ]
    assert original_readers == [RENDERER_READ]
    inputs = originals()
    for name in ("index.js", "leaflet.share.js", "leaflet.layers.js"):
        current = frontend_source(name, inputs[name])
        assert current == front["frontend_source"](name, inputs[name].decode())
        assert executable_source(current) == served["executable_source"](current)
    current = renderer_source(inputs["leaflet.osm.js"], TILES)
    record = renderer["require_exact_private_source"](
        inputs["leaflet.osm.js"].decode(), current, TILES
    )
    assert (
        record["payload_reduced"] is False and record["feature_order_changed"] is False
    )
    assert record["node_object_identity_preserved"] is True


@pytest.mark.parametrize("bad", [None, "", [], {}, 1, b"", b"wrong", "wrong"])
def test_wrong_original_sources_refused(bad: Any) -> None:
    with pytest.raises(ValueError):
        frontend_source("index.js", bad)
    with pytest.raises(ValueError):
        renderer_source(bad, TILES)
    with pytest.raises(ValueError):
        reviewed_sources(bad, TILES)


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        "https://127.0.0.1:2",
        "http://example.org:2",
        "http://127.0.0.1:2/",
        "http://user@127.0.0.1:2",
        "http://127.0.0.1:2?x=1",
    ],
)
def test_wrong_private_tile_origin_refused(url: Any) -> None:
    with pytest.raises(ValueError):
        renderer_source(originals()["leaflet.osm.js"], url)


@pytest.mark.parametrize("bundled", [False, True])
def test_full_actual_response_records_and_runtime_match(
    tmp_path: Path, bundled: bool
) -> None:
    c, page, responses, original, writer, authority = served_case(tmp_path)
    if bundled:
        responses = [
            Response(
                page,
                "application.debug-deadbeef.js",
                b"\n".join(r.raw for r in responses),
            )
        ]
    for response in responses:
        page.listener(response)
    assert all(r.reads == 0 for r in responses)
    c.verify(page, original, guard())
    assert c.state == "verified" and page.listener is None and page.renderer_reads == 1
    assert all(r.reads == 1 for r in responses)
    with pytest.raises(InvalidTransition):
        c.verify(page, original, guard())
    c.close(guard())
    c.close(guard())
    reader = MapArtifactReader(writer.plan, tmp_path, authority)
    handle = writer.seal(guard())
    summary = json.loads(reader.read(handle, "map-actually-served.json", guard()))
    assert summary["passed"] and len(summary["matched_sources"]) == 4
    assert summary["original_source_pins"] == {
        name: hashlib.sha256(raw).hexdigest() for name, raw in originals().items()
    }
    assert summary["expected_source_pins"] == {
        name: hashlib.sha256(source.encode()).hexdigest()
        for name, source in c.expected.sources
    }
    assert summary["private_tile_origin"] == TILES
    assert summary["original_readout"] == original.model_dump(mode="json")
    for i, response in enumerate(responses):
        assert reader.read(handle, f"map-served-{i}.js", guard()) == response.raw


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "status",
        "body",
        "utf8",
        "runtime",
        "foreign",
        "frame",
        "worker",
        "body-read",
        "detach",
        "expired",
    ],
)
def test_served_failure_retained_without_repeat(tmp_path: Path, fault: str) -> None:
    c, page, responses, original, writer, authority = served_case(tmp_path)
    if fault == "missing":
        responses.pop()
    if fault == "status":
        responses[0].status = 500
    if fault == "body":
        responses[0].raw = b"// wrong source"
    if fault == "utf8":
        responses[0].raw = b"\xff"
    if fault == "runtime":
        page.runtime = None
    if fault == "foreign":
        responses[0].url = "http://127.0.0.1:9/assets/index.js"
    if fault == "frame":
        responses[0].request.frame = object()
    if fault == "worker":
        responses[0].from_service_worker = True
    if fault == "body-read":
        responses[0].error = OSError("original body reply unknown")
    if fault == "detach":
        page.listener_fault = "detach"
    for response in responses:
        page.listener(response)
    with pytest.raises((EvidenceIntegrityError, ValueError, OSError, OperationStopped)):
        c.verify(page, original, guard(-1) if fault == "expired" else guard())
    assert c.state == "failed" and c.errors
    counts = [r.reads for r in responses]
    with pytest.raises(EvidenceIntegrityError):
        c.verify(page, original, guard())
    assert [r.reads for r in responses] == counts
    c.close(guard())
    handle = writer.seal(guard())
    saved = json.loads(
        MapArtifactReader(writer.plan, tmp_path, authority).read(
            handle, "map-actually-served.json", guard()
        )
    )
    assert not saved["passed"] and saved["error"]


def test_duplicate_callback_and_foreign_owner_refused(tmp_path: Path) -> None:
    c, page, responses, original, _, _ = served_case(tmp_path)
    with ThreadPoolExecutor(max_workers=1) as executor:
        with pytest.raises(OwnershipConflict):
            executor.submit(c.close, guard()).result(timeout=3)
    assert not c.close_attempted
    page.listener(responses[0])
    page.listener(responses[0])
    with pytest.raises(EvidenceIntegrityError):
        c.verify(page, original, guard())
    c.close(guard())
    assert not any(r.reads for r in responses)


@pytest.mark.parametrize("fault", ["attach", "runtime", "none"])
def test_composed_served_proof_closes_original_resources(
    tmp_path: Path, fault: str
) -> None:
    requests, writer, _, _, spec = collection(tmp_path, ORIGIN)
    served = NativeServedCapture(
        writer.plan, writer, guard(30), ORIGIN, originals(), TILES
    )
    collector = MapNativeProcessCollector(requests, served=served)
    page = ServedPage()
    try:
        if fault == "attach":
            page.listener_fault = "attach"
            with pytest.raises(OSError):
                collector.attach(page, spec, guard())
        else:
            collector.attach(page, spec, guard())
            for name, source in served.expected.sources:
                page.listener(Response(page, name, source.encode()))
            original = readout(spec, 0)
            if fault == "runtime":
                page.runtime = {}
                with pytest.raises(EvidenceIntegrityError):
                    collector.observe(page, original, guard())
                with pytest.raises(EvidenceIntegrityError):
                    collector.before_action(guard())
            else:
                collector.observe(page, original, guard())
                assert served.state == "verified" and requests.last_readout is original
                collector.finish(guard())
                assert page.renderer_reads == 1
    finally:
        collector.close(guard())
    assert (
        requests.relay.physical_closed
        and requests.state == "closed"
        and page.listener is None
    )


def test_candidate_asset_names_preserve_original_variants() -> None:
    assert candidate_names(ORIGIN + "/assets/index.debug-ab012.js?body=1") == (
        "index.js",
    )
    assert candidate_names(ORIGIN + "/assets/application-0123.js") == (
        "leaflet.osm.js",
    )
    assert candidate_names(ORIGIN + "/assets/unrelated.js") == ()
    assert (
        executable_source("// keep\n//= require dep\n//= require_self\nvar x=1;")
        == "// keep\nvar x=1;"
    )

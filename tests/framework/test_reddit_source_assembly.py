"""Current shared engineering judgment/source factories, explicit synthetic effects."""

from pathlib import Path
from reddit_source_selection import RedditSourceSelection
import json
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.evidence import EvidenceRef
from source_task_evaluation import judge_source_task
from reddit_evaluator_fixtures import evaluation_case
from reddit_preparation_fixtures import put
from reddit_browser_native import initialization
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "missing", ["none", "page_capture", "trace_ref", "trace_snapshot_ref"]
)
def test_shared_judgment_consumes_original_selected_request_and_capture_pairs(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch) as c:
        p = c.source.preparation

        def publish(value: Contract) -> EvidenceRef:
            return put(p.store, value)

        native = SimpleNamespace(
            public=p.inputs.public_task,
            binding=p.inputs.binding,
            binding_ref=c.contract.task_contract_ref,
            put=publish,
        )
        source: Any = SimpleNamespace(
            native=native,
            c=SimpleNamespace(
                evidence=p.store,
                spec=SimpleNamespace(configuration=SimpleNamespace(site_id="reddit")),
            ),
            saved={
                "environment_selection_ref": c.selected.environment_ref,
                "browser_spec_ref": c.selected.browser_spec_ref,
                "baseline_inputs": SimpleNamespace(
                    prepared=SimpleNamespace(scope=c.trace.scope)
                ),
            },
        )
        facts = {
            "catalog_" + label: pair.model_dump(mode="json")
            for label, pair in (
                ("before", c.selected.before),
                ("after", c.selected.after),
            )
            if pair is not None
        }
        assert (
            c.selected.page is not None
            and c.selected.trace_ref is not None
            and c.selected.trace_snapshot_ref is not None
        )
        actor = {
            "page_capture": c.selected.page.model_dump(mode="json"),
            "trace_ref": c.selected.trace_ref.model_dump(mode="json"),
            "trace_snapshot_ref": c.selected.trace_snapshot_ref.model_dump(mode="json"),
        }
        if missing != "none":
            actor.pop(missing)
        calls = p.native.reader.calls
        result = judge_source_task(source, facts, actor)
        assert result["evaluation"]["status"] == (
            "success" if missing == "none" else "unknown"
        )
        assert p.native.reader.calls == calls


def test_native_browser_factory_uses_original_reference_account_and_photo_scope(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with evaluation_case(tmp_path, node_path, monkeypatch, saved=False) as c:
        p = c.source.preparation
        publication = p.records.publish(p.inputs.selection, p.inputs.request.operation)
        native: Any = SimpleNamespace(
            c=SimpleNamespace(
                evidence=p.store, spec=SimpleNamespace(configuration=p.configuration)
            ),
            request=p.inputs.request,
            result=p.inputs.result,
            records=p.records,
            put=lambda value: put(p.store, value),
        )
        expected = c.browser.configuration.initialization
        calls = p.native.reader.calls
        assert initialization(native, c.source.started, publication) == expected
        assert initialization(native, c.source.started, publication) == expected
        assert p.native.reader.calls == calls
        native.request = None
        with pytest.raises(AssertionError):
            initialization(native, c.source.started, publication)


@pytest.mark.parametrize("fault", ["none", "wrong_snapshot", "missing_closure"])
def test_shared_source_preparation_unique_observation_capture_and_full_reset(
    tmp_path: Path, node_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    check_shared_source(tmp_path, node_path, monkeypatch, fault)


def check_shared_source(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    selection: RedditSourceSelection | None = None,
) -> None:
    from lab_generate_skill.domain.preparation_record import PreparedPublication
    from lab_generate_skill.sites.reddit.tasks.image_recovery import ImageObserved
    from site_capture_native import capture_original
    from reddit_source_assembly_fixture import shared_source

    with shared_source(tmp_path, node_path, monkeypatch, selection=selection) as c:
        source = c.source
        native, site = source.native, source.site
        if selection is not None:
            assert native.public == selection.public_at(
                site.site.instance.endpoint, None
            )
        original = c.request("snapshot")
        result = site.tasks.execute_task(original, control=guard())
        ref = native.raw(result.private_result.encode(), "reddit-image-recovery/2")
        if fault == "wrong_snapshot":
            with pytest.raises(AssertionError):
                source.after_snapshot(
                    original.model_copy(update={"binding_ref": native.spec_ref}),
                    result,
                    ref,
                )
            assert "environment_ref" not in source.saved
            return
        source.after_snapshot(original, result, ref)
        request = c.request("prepare", ref)
        prepared = site.tasks.execute_task(request, control=guard())
        publication = native.publish(
            request, prepared, site.site.instance, environment=source.environment
        )
        before = capture_original(c.site, site, request, "before")
        observed = source.observe(
            PreparedPublication.model_validate(publication["publication"]),
            tmp_path / "browser",
            monkeypatch,
        )
        assert (
            observed["complete_baseline"] and source.saved["baseline"].status == "ready"
        )
        assert c.browsers[0].channels[0].engine.calls == ["start", "close"]
        after = capture_original(c.site, site, request, "after")
        first = ImageObserved.model_validate_json(json.dumps(before["catalog"]))
        last = ImageObserved.model_validate_json(json.dumps(after["catalog"]))
        assert c.site.evidence.read(first.native.payload_ref) == c.site.evidence.read(
            last.native.payload_ref
        )
        assert source.saved["browser_closed_before_restore"]
        restore = c.request("restore", ref)
        restored = site.tasks.execute_task(restore, control=guard())
        if fault == "missing_closure":
            source.saved["browser_closed_before_restore"] = False
            with pytest.raises(AssertionError):
                source.after_restore(restore, restored)
            assert len(c.native.task.instance.generations) == 2
            return
        reset = source.after_restore(restore, restored)
        assert (
            reset["reset_status"] == "safe" and source.saved["reset"].status == "safe"
        )
        assert len(c.native.task.instance.generations) == 3

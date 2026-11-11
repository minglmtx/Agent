"""Existing Shopping facts drive actual entry branches and internal reuse."""

from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from lab_generate_skill.adapters.storage.preparations import EvidencePreparationRecords
from lab_generate_skill.bootstrap.source_qualification_records import (
    SourceQualificationRecords,
)
from lab_generate_skill.bootstrap.shopping_category_source_inputs import (
    prepare_category_source_delta,
    load_category_source_delta,
)
from lab_generate_skill.domain.errors import OwnershipConflict
from shopping_category_source_fixtures import source_unit_case
from test_shopping_category_navigation_input import originals as originals, reference
from test_slurm_commands import guard
from site_instance_fixtures import node_path as node_path
import lab_generate_skill.bootstrap.shopping_category_source_inputs as inputs
from lab_generate_skill.bootstrap.shopping_category_navigation import (
    load_category_navigation_inputs,
)
import lab_generate_skill.bootstrap.shopping_category_cli as cli
import lab_generate_skill.bootstrap.shopping_category_production_entry as entry
import test_shopping_category_production_entry as original_entry

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
C = W / "experiments/framework-combined-release-20261030-v1"


def delta_for(original: Any, complete: Path | None = None) -> dict[str, Any]:
    raw, _, public = original
    return prepare_category_source_delta(
        C / "shopping18-source-inventory-4953423/inventory.json",
        C / "shopping18-source-compatibility-4956269/compatibility.json",
        reference(raw),
        public,
        (C / "shopping-return-pinned-failed-first-4953319/scoped-acceptance.json",),
        guard(60),
        complete_material=complete,
    )


def write_delta(path: Path, delta: dict[str, Any]) -> str:
    path.write_text(json.dumps(delta))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_all18_selected_bodies_decode_once_without_historical_or_native_reread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
) -> None:
    prepared = [(o, delta_for(o)) for o in originals]
    original_open = Path.open
    decode = load_category_navigation_inputs
    forbidden = {Path(x["path"]) for _, d in prepared for x in d["found_artifacts"]}
    forbidden.update(Path(d["inventory"]["path"]) for _, d in prepared)
    decoded = []

    def opened(path: Path, *a: Any, **kw: Any) -> Any:
        assert (
            path not in forbidden
        ), "Reused Shopping artifact reopened by selected consumer"
        return original_open(path, *a, **kw)

    def once(*a: Any, **kw: Any) -> Any:
        decoded.append(a[1])
        return decode(*a, **kw)

    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(inputs, "load_category_navigation_inputs", once)
    for i, (original, delta) in enumerate(prepared):
        raw, _, public = original
        p = tmp_path / (str(i) + ".json")
        sha = write_delta(p, delta)
        loaded = load_category_source_delta(
            p, sha, raw, reference(raw), public, guard(60)
        )
        for _ in range(3):
            assert loaded.require(raw, reference(raw), public) is loaded.selected
        assert loaded.material is None
        assert loaded.delta["execution"]["historical_validator_calls"] == 0
        assert loaded.delta["execution"]["common_check_or_install_calls"] == 0
    assert len(decoded) == 18


@pytest.mark.parametrize(
    "fault",
    [
        "pin",
        "native",
        "reference",
        "history",
        "mode",
        "supplement",
        "private",
        "public",
        "grant",
        "common",
        "complete_missing",
    ],
)
def test_invalid_selected_delta_is_refused_without_reconstruction(
    tmp_path: Path,
    originals: Any,
    fault: str,
) -> None:
    original = originals[0]
    raw, _, public = original
    delta = delta_for(original)
    if fault == "native":
        delta["native_contract"]["sha256"] = "0" * 64
    elif fault == "reference":
        delta["native_reference"]["producer"] = "foreign"
    elif fault == "history":
        delta["found_artifacts"] = []
    elif fault == "mode":
        delta["execution"]["mode"] = "build_all"
    elif fault == "supplement":
        delta["execution"]["supplement"] = []
    elif fault == "private":
        delta["selected"]["private_spec"]["original"]["completion"][
            "heading_regex"
        ] = "wrong"
    elif fault == "public":
        delta["selected"]["public_task"]["goal"] = "foreign"
    elif fault == "grant":
        delta["runtime_or_resume_authority"] = True
    elif fault == "common":
        delta["common_evidence"] = []
    elif fault == "complete_missing":
        delta["complete_material"] = {
            "path": str(tmp_path / "missing.json"),
            "sha256": "0" * 64,
            "size_bytes": 1,
        }
        delta["execution"].update(
            mode="consume_complete", source_producer_calls=0, supplement=[]
        )
    p = tmp_path / "delta.json"
    sha = write_delta(p, delta)
    with pytest.raises((ValueError, OwnershipConflict, FileNotFoundError)):
        load_category_source_delta(
            p,
            "0" * 64 if fault == "pin" else sha,
            raw,
            reference(raw),
            public,
            guard(60),
        )


@pytest.mark.parametrize(
    "fault", ["none", "capture", "cancel-after-reset", "restore-return-lost"]
)
def test_source_internal_tripwires_keep_current_instance_actions_and_cleanup(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    held = []
    reads: Counter[int] = Counter()
    checks: Counter[int] = Counter()
    actions = []
    define = SourceQualificationRecords.define
    read = EvidencePreparationRecords._read_inputs
    task = SourceQualificationRecords.request

    def defined(records: SourceQualificationRecords, *a: Any, **kw: Any) -> Any:
        result = define(records, *a, **kw)
        held.append(records)
        assert records.records is not None and records.input_bodies is not None
        checker = records.records.checks
        check = getattr(checker, "check_with_bodies")

        def checked(*a: Any, **kw: Any) -> Any:
            checks[id(records)] += 1
            assert checks[id(records)] == 1, "Source pure check repeated"
            return check(*a, **kw)

        monkeypatch.setattr(checker, "check_with_bodies", checked)
        return result

    def reading(records: EvidencePreparationRecords, *a: Any, **kw: Any) -> Any:
        if records.record_inputs is not None:
            reads[id(records)] += 1
            assert reads[id(records)] == 1, "Source preparation graph reread"
        return read(records, *a, **kw)

    def requested(
        records: SourceQualificationRecords, action: str, *a: Any, **kw: Any
    ) -> Any:
        actions.append(action)
        return task(records, action, *a, **kw)

    monkeypatch.setattr(SourceQualificationRecords, "define", defined)
    monkeypatch.setattr(EvidencePreparationRecords, "_read_inputs", reading)
    monkeypatch.setattr(SourceQualificationRecords, "request", requested)
    c = source_unit_case(tmp_path, node_path, monkeypatch, originals[0], fault)
    if fault == "none":
        result = c.run()
        facts = result.source_prefix_reuse
        assert result is c.publications[0] and result.receipt.scope == c.owner.scope
    else:
        from lab_generate_skill.bootstrap.shopping_category_source_qualification import (
            CategoryNavigationSourceUnconfirmed,
        )

        with pytest.raises(CategoryNavigationSourceUnconfirmed) as caught:
            c.run()
        facts = caught.value.progress.input_reuse
        assert not c.publications and not caught.value.actual_actor_dispatched
    assert len(held) == 1 and actions == ["snapshot", "prepare", "restore"]
    records = held[0]
    assert records.input_bodies is not None and records.records is not None
    assert facts is not None
    assert (
        facts["preparation_graph_reads"]
        == facts["publication_reads"]
        == facts["checks_executed"]
        == 1
    )
    assert facts["preparation_graph_reuses"] > 0 and facts["checks_reused"] > 0
    assert reads[id(records.records)] == checks[id(records)] == 1
    assert (
        not records.input_bodies.active and records.input_bodies.records.graph is None
    )
    assert records.input_bodies.prepared_browser is None
    op = c.site.op.cleanup(
        "source-prefix-final-read", now=c.site.clock.utcnow(), seconds=30
    )
    assert c.site.journal.read(c.site.spec.token, op).state == "closed"
    assert records.progress.restore_attempted
    if fault != "restore-return-lost":
        assert records.progress.reset is not None
        assert records.progress.reset.status == "safe"


@pytest.mark.parametrize("complete", [False, True])
def test_real_business_entry_consumes_selected_body_without_second_decode(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    complete: bool,
) -> None:
    c = original_entry.runtime_case(tmp_path, node_path, monkeypatch, originals[0])
    raw, _, _ = originals[0]
    public = c.published.inputs.context.task
    material = tmp_path / "complete.json"
    material.write_text(c.published.material.model_dump_json())
    delta = delta_for((raw, None, public), material if complete else None)
    path = tmp_path / "delta.json"
    sha = write_delta(path, delta)
    loaded = load_category_source_delta(
        path, sha, raw, reference(raw), public, guard(60)
    )
    assert loaded.material == (c.published.material if complete else None)
    c.runtime = replace(c.runtime, source_inputs=loaded)
    monkeypatch.setattr(original_entry, "runtime_case", lambda *a, **kw: c)

    def forbidden(*a: Any, **kw: Any) -> Any:
        pytest.fail("Selected native body decoded again in business entry")

    monkeypatch.setattr(entry, "load_category_navigation_inputs", forbidden)
    original_entry.test_real_entry_reuses_original_bodies_then_reaches_claimed_phase_consumer(
        tmp_path,
        node_path,
        monkeypatch,
        originals,
        "deferred-retained" if complete else "deferred-new",
        "selected-retention",
    )


def test_cli_passes_selected_partial_inputs_to_original_supplier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
) -> None:
    raw, _, public = originals[0]
    delta = delta_for(originals[0])
    path = tmp_path / "delta.json"
    sha = write_delta(path, delta)
    native = tmp_path / "native.json"
    native.write_bytes(raw)
    ref = tmp_path / "ref.json"
    ref.write_text(reference(raw).model_dump_json())
    task = tmp_path / "public.json"
    task.write_text(public.model_dump_json())
    accepted = json.loads(
        (
            C / "shopping-return-pinned-runtime-install-4953369/acceptance.json"
        ).read_bytes()
    )
    supplied = Path(accepted["records"][0]["supplier_inputs"])
    seen = []

    @contextmanager
    def supplier(*a: Any, **kw: Any) -> Any:
        loaded = kw["source_inputs"]
        assert loaded.require(a[1], a[2], a[3]).public_task == public
        assert loaded.material is None and kw["source_index"] == C / "batch-plan.json"
        seen.append(loaded)
        yield SimpleNamespace(runtime="original-runtime", facts={})

    def execute(runtime: Any, *a: Any) -> None:
        assert runtime == "original-runtime" and a[:3] == (raw, reference(raw), public)

    monkeypatch.setattr(cli, "supply_category_runtime", supplier)
    monkeypatch.setattr(cli, "run_category_production", execute)
    monkeypatch.setattr(
        "sys.argv",
        [
            "category",
            "--supplier-inputs",
            str(supplied),
            "--native-input",
            str(native),
            "--native-reference",
            str(ref),
            "--public-task",
            str(task),
            "--output",
            str(tmp_path),
            "--claim-root",
            str(tmp_path),
            "--claim-scope",
            "unit-category",
            "--source-index",
            str(C / "batch-plan.json"),
            "--source-delta",
            str(path),
            "--source-delta-sha256",
            sha,
        ],
    )
    cli.main()
    assert len(seen) == 1


@pytest.mark.parametrize("fault", ["half", "material-conflict"])
def test_cli_rejects_missing_delta_half_or_conflicting_source_before_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    argv = [
        "category",
        "--supplier-inputs",
        "absent",
        "--native-input",
        "absent",
        "--native-reference",
        "absent",
        "--public-task",
        "absent",
        "--output",
        str(tmp_path),
        "--claim-root",
        str(tmp_path),
        "--claim-scope",
        "unit-category",
        "--source-delta",
        "absent",
    ]
    if fault == "material-conflict":
        argv += ["--source-delta-sha256", "0" * 64, "--retained-source", "absent"]
    monkeypatch.setattr("sys.argv", argv)

    def forbidden(*a: Any, **kw: Any) -> Any:
        pytest.fail("Invalid delta reached input/resource work")

    monkeypatch.setattr(cli, "_document", forbidden)
    with pytest.raises(ValueError):
        cli.main()

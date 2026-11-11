"""New source consumer against retained train public pages; never replay actions."""

from pathlib import Path
import hashlib
import json
import re
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.context_preparation import ContextPreparationReceipt
from lab_generate_skill.domain.context_projection import ActorContextSource
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.observation import ResolvedObservation, Observation
from lab_generate_skill.domain.observation_read import ObservationRegionRange
from lab_generate_skill.domain.trace_journal import TraceSnapshot
from lab_generate_skill.policies.observation_index import index_public_ax
from lab_generate_skill.policies.observation_search import literal_search
from observation_read_fixtures import policy

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
C = W / "experiments/framework-combined-release-20261030-v1"


def body(root: Path, reference: EvidenceRef) -> bytes:
    raw = (root / "evidence/blobs" / reference.sha256).read_bytes()
    assert (
        len(raw) == reference.size_bytes
        and hashlib.sha256(raw).hexdigest() == reference.sha256
    )
    return raw


def test_retained_admin_200_rows_last_row_headers_and_complete_ids_are_addressable() -> (
    None
):
    root = (
        W
        / "experiments/framework-admin-navigation-production-20261102-v1/production-4955553"
    )
    proof = json.loads(
        (
            C / "adaptive-public-source-4957565/source-and-public-structure.json"
        ).read_bytes()
    )
    rp = (
        root
        / "evidence/blobs/86a8e12f3c42dadd11a821a93a094a4706e0ca174d3e8f1558a59262bafdcc30"
    )
    raw = rp.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == proof["pins"][str(rp)]
    receipt = ContextPreparationReceipt.model_validate_json(raw)
    source = receipt.request.source
    assert isinstance(source, ActorContextSource) and source.scope.task.split == "train"
    turn = ActorPublicTurn.model_validate_json(body(root, source.turn_ref))
    tracepath = next((root / "trace").glob("*.trace.json"))
    trace = TraceSnapshot.model_validate_json(tracepath.read_bytes())
    assert trace.plan.scope == source.scope
    reference = trace.project().current_observation(trace.plan)
    raw_observation = body(root, reference)
    assert Observation.model_validate_json(raw_observation) == turn.observation.record
    index = index_public_ax(
        reference, raw_observation, turn.observation, source.scope, policy()
    )
    tables = [r for r in index.regions if r.kind == "table"]
    assert len(tables) == 1
    table = tables[0]
    assert len(table.data_row_spans) == 200
    assert (
        len(
            re.findall(
                r"\bcolumnheader\b",
                "".join(index.source(s) for s in table.header_spans),
            )
        )
        == 15
    )
    last = ObservationRegionRange(
        region_id=table.region_id, unit="data_rows", start=199, end=200
    )
    returned = index.fragments((last,))
    contents = [piece for piece in returned if piece.purpose == "content"]
    assert len(contents) == 1 and contents[0].span == table.data_row_spans[-1]
    assert len(re.findall(r"\bgridcell\b", contents[0].text)) == 15
    assert any(piece.purpose == "table_header" for piece in returned)
    old_ids = re.findall(r"(?m)^\t*\[([0-9]+)\]", index.text)
    assert old_ids == [node.node_id for node in index.nodes if node.node_id is not None]
    whole = index.fragments(
        (ObservationRegionRange(region_id="ax-line-0", unit="whole_region"),)
    )
    assert len(whole) == 1 and whole[0].text == index.text
    assert (
        receipt.decision is not None
        and receipt.decision.reason_code == "input_budget_exceeded"
    )
    assert receipt.decision.assessments[0].input_tokens == 98037


def test_retained_map_navigation_source_remains_exact_and_searches_only_public_snapshot() -> (
    None
):
    root = (
        W
        / "experiments/framework-map-navigation42-production-20261102-v1/production-4955053"
    )
    proof = json.loads(
        (
            C / "adaptive-public-source-4957565/source-and-public-structure.json"
        ).read_bytes()
    )
    row = next(r for r in proof["rows"] if r["site"] == "map")
    reference = EvidenceRef.model_validate_json(json.dumps(row["snapshot_ref"]))
    raw = body(root, reference)
    record = Observation.model_validate_json(raw)
    assert record.text_ref is None and record.text is not None
    trace = TraceSnapshot.model_validate_json(
        next((root / "trace").glob("*.trace.json")).read_bytes()
    )
    resolved = ResolvedObservation(record=record, text=record.text)
    index = index_public_ax(reference, raw, resolved, trace.plan.scope, policy())
    assert len(index.nodes) == 95 and index.text == record.text
    fragments = index.fragments(
        (ObservationRegionRange(region_id="ax-line-0", unit="whole_region"),)
    )
    assert len(fragments) == 1 and fragments[0].text == record.text
    # Scope of no-hit is this captured page, never another tab/site/backend.
    result = literal_search(index, "absent-literal-for-public-scope", ())
    assert result.coverage_complete and result.results_exhausted and not result.hits

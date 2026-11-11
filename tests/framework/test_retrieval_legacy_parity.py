"""Isolated comparisons to old selection/filter code, never a runtime import.

This checks policy arithmetic only; no encoder, model or actual bank is run.
"""

import json
import subprocess
import sys

import pytest

from lab_generate_skill.domain.data_scope import normalized_goal
from lab_generate_skill.domain.retrieval import (
    SkillScore,
    eligible_records,
    rank_retrieval,
)
from retrieval_fixtures import fixture


@pytest.mark.parametrize("mode", ["ties", "source_alias", "excluded_cluster_member"])
def test_original_filter_normalization_and_top_six(mode: str) -> None:
    data = fixture()
    scope = data.scope
    if mode == "source_alias":
        scope = scope.model_copy(update={"excluded_source_ids": ("runtime-0",)})
    if mode == "excluded_cluster_member":
        scope = scope.model_copy(
            update={
                "excluded_skill_ids": (
                    data.bank.records[1].sources[0].candidate_skill_id,
                )
            }
        )
    eligible = eligible_records(data.query, scope, data.bank, data.split)
    values = (
        [1.0] * len(eligible)
        if mode == "ties"
        else [-float(i % 3) for i in range(len(eligible))]
    )
    scores = tuple(
        SkillScore(skill_id=r.skill_id, score=s) for r, s in zip(eligible, values)
    )
    result = rank_retrieval(
        data.query, scope, data.bank, data.split, scores, data.result.score_evidence_ref
    )
    rows = []
    for record in data.bank.records:
        members = [data.split.member(source.task) for source in record.sources]
        rows.append(
            dict(
                skill_id=record.skill_id,
                domain=record.sources[0].task.site,
                **record.skill.model_payload(),
                source_task_ids=sorted(
                    {identity for member in members for identity in member.source_ids}
                ),
                source_goals=[m.public_goal for m in members],
                source_generation_ids=[s.generation_id for s in record.sources],
            )
        )
    texts = ["  ＡＢＣ\nStraße\tX ", "abc STRASSE x", "Public goal target"]
    program = """
import json,sys
from lab_generate_skill.data_scope import filter_bank,norm
from lab_generate_skill.stage1_retrieval_ready import select_references
p=json.load(sys.stdin)
rows,removed=filter_bank(p['rows'],set(p['blocked']),{('map',norm(p['goal']))},excluded_skill_ids=p['excluded'])
refs=select_references(rows,p['scores'])
print(json.dumps({'eligible':[r['skill_id'] for r in rows],'hits':[r['skill_id'] for r in refs],'normalized':[norm(t) for t in p['texts']]}))
"""
    output = subprocess.run(
        [sys.executable, "-B", "-c", program],
        input=json.dumps(
            dict(
                rows=rows,
                blocked=scope.excluded_source_ids,
                excluded=scope.excluded_skill_ids,
                goal=data.query.literal_goal,
                scores=values,
                texts=texts,
            )
        ),
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    actual = json.loads(output.stdout)
    assert actual == {
        "eligible": [r.skill_id for r in eligible],
        "hits": [h.skill_id for h in result.hits],
        "normalized": [normalized_goal(t) for t in texts],
    }

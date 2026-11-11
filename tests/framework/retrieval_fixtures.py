"""Explicit training-only unit bank, not a qualified production source."""

import hashlib
import json
from dataclasses import dataclass

from evidence_control_fixtures import EvidenceFixtureStore as FileEvidenceStore
from lab_generate_skill.domain.bank import BankManifest, SkillRecord, SkillSource
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.data_scope import SplitMember, SplitManifest
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.identity import TaskIdentity, Split, Site
from lab_generate_skill.domain.retrieval import (
    RetrievalQuery,
    RetrievalScope,
    RetrievalResult,
    ScoringReceipt,
    SkillScore,
    rank_retrieval,
)
from lab_generate_skill.domain.validation import Contract
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.encoding import (
    EncoderFiles,
    EncoderConfig,
    EncodedScores,
)
from lab_generate_skill.domain.retrieval_encoding import (
    RetrievalIndex,
    IndexEntry,
    document_texts,
)
from lab_generate_skill.domain.retrieval_execution import RetrievalExecution
from encoder_fixtures import model_files, config
from test_construction_state import skill
from test_run_journal import command
from observation_fixtures import sample_observation


def reference(
    value: object,
    schema: str = "fixture/1",
    visibility: str = "private",
    store: FileEvidenceStore | None = None,
) -> EvidenceRef:
    raw = (
        value.model_dump_json().encode()
        if isinstance(value, Contract)
        else json.dumps(value, sort_keys=True).encode()
    )
    metadata = EvidenceMetadata.model_validate(
        dict(
            media_type="application/json",
            content_schema=schema,
            visibility=visibility,
            producer="unit-retrieval",
        )
    )
    if store is not None:
        return store.put(raw, metadata)
    digest = hashlib.sha256(raw).hexdigest()
    return EvidenceRef(
        uri="cas://sha256/" + digest,
        sha256=digest,
        size_bytes=len(raw),
        media_type=metadata.media_type,
        content_schema=schema,
        visibility=metadata.visibility,
        producer=metadata.producer,
    )


def member(
    name: str, split: Split = "train", goal: str | None = None, *, site: Site = "map"
) -> SplitMember:
    return SplitMember(
        identity=TaskIdentity(
            source_task_id="source-" + name,
            task_id="task-" + name,
            split=split,
            site=site,
            family="unit",
            contract_version=1,
        ),
        goal_group_id="group-" + name,
        public_goal=goal or "Public goal " + name,
        aliases=("runtime-" + name,),
    )


@dataclass
class RetrievalFixture:
    split: SplitManifest
    bank: BankManifest
    query: RetrievalQuery
    scope: RetrievalScope
    result: RetrievalResult
    context: PublicConstructionContext


def fixture(
    store: FileEvidenceStore | None = None,
    target_split: Split = "train",
    *,
    encoder_files: EncoderFiles | None = None,
    encoder_config: EncoderConfig | None = None,
    public_context: PublicConstructionContext | None = None,
    public_context_ref: EvidenceRef | None = None,
) -> RetrievalFixture:
    if public_context_ref is not None:
        if public_context is None or store is None:
            raise ValueError(
                "Original context reference requires its full context and store"
            )
        declared = EvidenceRef.model_validate(public_context_ref)
        if (declared.content_schema, declared.visibility, declared.media_type) != (
            "public-construction-context/1",
            "public",
            "application/json",
        ) or store.read(declared) != public_context.model_dump_json().encode():
            raise ValueError(
                "Original public context reference differs from complete bytes/type"
            )
    site: Site = (
        public_context.task.identity.site if public_context is not None else "map"
    )
    sources = tuple(member(str(i), site=site) for i in range(8))
    target = member("target", target_split, site=site)
    if public_context is not None:
        if public_context.task.identity.split != target_split:
            raise ValueError("Fixture context must match the declared target split")
        target = target.model_copy(
            update={
                "identity": public_context.task.identity,
                "public_goal": public_context.task.goal,
            }
        )
    split = SplitManifest(partition_id="unit", members=(*sources, target))
    split_ref = reference(split, "data-split/1", store=store)
    records = []
    for i, source in enumerate(sources):
        generation = "generation-" + str(i)
        content = skill(str(i))
        records.append(
            SkillRecord(
                skill_id="skill-" + str(i),
                skill=content,
                skill_ref=reference(content, "compact-skill/1", "public", store),
                content_digest=content.content_digest,
                sources=(
                    SkillSource(
                        task=source.identity,
                        goal_group_id=source.goal_group_id,
                        generation_id=generation,
                        candidate_skill_id="candidate_"
                        + hashlib.sha256(generation.encode()).hexdigest()[:20],
                        trajectory_ref=reference(
                            {"source": source.identity.task_id}, store=store
                        ),
                        review_ref=reference({"reviewed": True}, store=store),
                    ),
                ),
                build_release_ref=reference({"release": "unit"}, store=store),
            )
        )
    encoder_files = encoder_files or model_files()
    encoder_config = encoder_config or config()
    model_ref = reference(encoder_files, "encoder-files/1", store=store)
    config_ref = reference(encoder_config, "encoder-config/1", store=store)
    index_ref = reference(
        RetrievalIndex(
            entries=tuple(
                IndexEntry(skill_id=r.skill_id, content_digest=r.content_digest)
                for r in records
            )
        ),
        "retrieval-index/1",
        store=store,
    )
    bank = BankManifest(
        bank_id="unit",
        split_ref=split_ref,
        encoder_ref=model_ref,
        tokenizer_ref=model_ref,
        index_ref=index_ref,
        retrieval_config_ref=config_ref,
        records=tuple(records),
    )
    scope = RetrievalScope(
        bank_ref=reference(bank, "bank-manifest/1", store=store), split_ref=split_ref
    )
    context = public_context or PublicConstructionContext(
        context_id="context",
        task=PublicTask(
            identity=target.identity,
            goal=target.public_goal,
            start_url="https://map.example/",
            allowed_actions=("stop",),
        ),
        initial_observation_ref=reference(
            sample_observation(target.identity), "observation/1", "public", store
        ),
    )
    query = RetrievalQuery(
        task=target.identity,
        literal_goal=target.public_goal,
        public_context_ref=public_context_ref
        or reference(context, "public-construction-context/1", "public", store),
    )
    scores = tuple(SkillScore(skill_id=r.skill_id, score=1.0) for r in bank.records)
    documents = document_texts(bank.records)
    encoded = EncodedScores(
        model_files_sha256=encoder_files.digest,
        config_sha256=hashlib.sha256(
            encoder_config.model_dump_json().encode()
        ).hexdigest(),
        documents_sha256=hashlib.sha256(
            json.dumps(documents, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest(),
        query_sha256=hashlib.sha256(query.literal_goal.encode()).hexdigest(),
        document_vectors_sha256="0" * 64,
        query_vector_sha256="0" * 64,
        scores=tuple(s.score for s in scores),
        documents_reused=False,
    )
    execution = RetrievalExecution(
        query=query, scope=scope, operation=command(), encoded=encoded
    )
    receipt = ScoringReceipt(
        query=query,
        scope=scope,
        encoder_ref=model_ref,
        tokenizer_ref=model_ref,
        index_ref=index_ref,
        config_ref=config_ref,
        scores=scores,
        execution_ref=reference(execution, "retrieval-execution/1", store=store),
    )
    result = rank_retrieval(
        query,
        scope,
        bank,
        split,
        scores,
        reference(receipt, "retrieval-scores/1", store=store),
    )
    return RetrievalFixture(split, bank, query, scope, result, context)

"""Shared read-only preparation for retrieval producers and consumers.

Reads exact CAS documents and all direct inputs. No model execution or approval:
semantic source/context/policy qualification is a separate mandatory port.
"""

from dataclasses import dataclass
from lab_generate_skill.adapters.plans.observations import ObservationReader

from lab_generate_skill.domain.bank import BankManifest, SkillRecord
from lab_generate_skill.domain.construction_inputs import PublicConstructionContext
from lab_generate_skill.domain.data_scope import SplitManifest
from lab_generate_skill.domain.encoding import EncoderFiles, EncoderConfig
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.retrieval import (
    RetrievalQuery,
    RetrievalScope,
    eligible_records,
)
from lab_generate_skill.domain.retrieval_encoding import RetrievalIndex
from lab_generate_skill.domain.skill import CompactSkill
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl


@dataclass(frozen=True)
class RetrievalInputs:
    bank: BankManifest
    split: SplitManifest
    context: PublicConstructionContext
    eligible: tuple[SkillRecord, ...]
    files: EncoderFiles
    config: EncoderConfig


class RetrievalInputReader:
    def __init__(self, store: EvidenceReader) -> None:
        self.store = store

    def read(self, ref: EvidenceRef, control: OperationControl) -> bytes:
        control.checkpoint()
        data = self.store.read(ref, control=control)
        control.checkpoint()
        return data

    def load(
        self, query: RetrievalQuery, scope: RetrievalScope, control: OperationControl
    ) -> RetrievalInputs:
        query = RetrievalQuery.model_validate(query)
        scope = RetrievalScope.model_validate(scope)
        bank = BankManifest.model_validate_json(self.read(scope.bank_ref, control))
        split = SplitManifest.model_validate_json(self.read(scope.split_ref, control))
        eligible = eligible_records(query, scope, bank, split)
        if len(eligible) < 6:
            raise ValueError("At least six eligible same-site skills required")
        context = PublicConstructionContext.model_validate_json(
            self.read(query.public_context_ref, control)
        )
        if (
            context.task.identity != query.task
            or context.task.goal != query.literal_goal
        ):
            raise OwnershipConflict(
                "Retrieval query differs from frozen public context"
            )
        ObservationReader(self.store).initial(context, control)
        files = EncoderFiles.model_validate_json(self.read(bank.encoder_ref, control))
        config = EncoderConfig.model_validate_json(
            self.read(bank.retrieval_config_ref, control)
        )
        index = RetrievalIndex.model_validate_json(self.read(bank.index_ref, control))
        index.check_records(bank.records)
        for record in bank.records:
            actual = CompactSkill.model_validate_json(
                self.read(record.skill_ref, control)
            )
            if actual != record.skill:
                raise OwnershipConflict("Stored bank skill differs from inline content")
            self.read(record.build_release_ref, control)
            for source in record.sources:
                self.read(source.trajectory_ref, control)
                self.read(source.review_ref, control)
        return RetrievalInputs(bank, split, context, eligible, files, config)

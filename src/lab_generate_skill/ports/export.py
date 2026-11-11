"""Qualified original export readers and actual source/fee/phase admission."""

from typing import Protocol
from lab_generate_skill.domain.export import (
    ExportPlan,
    ExportScope,
    ExportSource,
    ExportAdmission,
)
from lab_generate_skill.domain.export_material import ExportMaterial
from lab_generate_skill.domain.data_scope import SplitManifest
from lab_generate_skill.ports.lifecycle import OperationControl


class ExportInputs(Protocol):
    def load(
        self,
        source: ExportSource,
        plan: ExportPlan,
        scope: ExportScope,
        split: SplitManifest,
        control: OperationControl,
    ) -> ExportMaterial:
        """Recheck exact original evidence/review, public input/top6 and target.
        No model, native action, new capture or callback loaded from data.
        """
        ...


class ExportAuthority(Protocol):
    def verify_scope(
        self,
        plan: ExportPlan,
        scope: ExportScope,
        split: SplitManifest,
        control: OperationControl,
    ) -> None:
        """Actual fixed source/release/read/phase/authorization rights, not labels."""
        ...

    def admit(
        self,
        plan: ExportPlan,
        scope: ExportScope,
        source: ExportSource,
        material: ExportMaterial,
        control: OperationControl,
    ) -> ExportAdmission:
        """Verify actual formal source qualification and original paid ledger,
        native termination, loaded role/source and independent review provenance.
        Fixtures/engineering/pilot/local Teacher cannot be promoted. No default.
        """
        ...

"""Publish existing InitialStateChecks from original evidence; never navigate again."""

import hashlib
from lab_generate_skill.domain.initial_observation_publication import (
    PublishedInitialObservation,
)
from lab_generate_skill.adapters.plans.initial_observation import (
    InitialObservationReader,
)
from lab_generate_skill.domain.initial_observation import (
    InitialObservationSelection,
    InitialObservationInputs,
)
from lab_generate_skill.domain.preparation import PreparationReceipt
from lab_generate_skill.domain.baseline import InitialStateChecks
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.state_checks import StateChecks
from lab_generate_skill.domain.state_scope import StateCommitUnconfirmed
from lab_generate_skill.domain.errors import OwnershipConflict, EvidenceIntegrityError
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControls, OperationControl
from lab_generate_skill.ports.preparation_records import PreparationRecords
from lab_generate_skill.ports.initial_observation import (
    InitialObservationChecks,
    InitialObservationAuthority,
)


class EvidenceInitialObservations:
    def __init__(
        self,
        store: EvidenceStore,
        controls: OperationControls,
        preparations: PreparationRecords,
        checks: InitialObservationChecks,
        authority: InitialObservationAuthority,
    ) -> None:
        self.store, self.controls, self.checks, self.authority = (
            store,
            controls,
            checks,
            authority,
        )
        self.reader = InitialObservationReader(store, preparations)

    def _verify(
        self,
        selection: InitialObservationSelection,
        original: OperationContext,
        operation: OperationContext,
        control: OperationControl,
    ) -> InitialStateChecks:
        inputs = self.reader.load(selection, operation, control)
        return self._verify_inputs(inputs, original, operation, control)

    def _verify_inputs(
        self,
        inputs: InitialObservationInputs,
        original: OperationContext,
        operation: OperationContext,
        control: OperationControl,
    ) -> InitialStateChecks:
        inputs = InitialObservationInputs.model_validate(inputs)
        selection = inputs.selection
        scope = inputs.prepared.scope
        if (
            original.mode != "execute"
            or (original.run_id, original.owner_id, original.attempt_id)
            != (scope.owner.run_id, scope.owner.owner_id, scope.attempt_id)
            or original.operation_id
            in (
                inputs.returned.operation.operation_id,
                inputs.acquired.operation.operation_id,
            )
        ):
            raise OwnershipConflict(
                "Initial checks require their own original attempt operation"
            )
        if operation != original and not (
            operation.mode == "cleanup"
            and operation.parent_operation_id == original.operation_id
            and (
                operation.run_id,
                operation.owner_id,
                operation.attempt_id,
                operation.allocation_id,
                operation.recovery_ref,
            )
            == (
                original.run_id,
                original.owner_id,
                original.attempt_id,
                original.allocation_id,
                original.recovery_ref,
            )
        ):
            raise OwnershipConflict(
                "Initial checks require original operation or its read-only reconciliation"
            )
        checks = StateChecks.model_validate(self.checks.check(inputs, control))
        if checks.required != inputs.spec.initial_checks:
            raise OwnershipConflict(
                "Initial observation cannot narrow frozen check coverage"
            )
        self.reader.reads.dependencies((checks,), control)
        self.authority.verify(inputs, checks, operation, control)
        started = inputs.acquired.details.started
        return InitialStateChecks(
            scope=scope,
            operation=original,
            spec_ref=inputs.prepared.spec_ref,
            prepared_ref=selection.preparation.prepared_ref,
            observation_ref=started.initial_observation_ref,
            checks=checks,
            measured_state_sha256=started.initial_observation_ref.sha256,
        )

    def publish(
        self, selection: InitialObservationSelection, operation: OperationContext
    ) -> EvidenceRef:
        selection = InitialObservationSelection.model_validate(selection)
        operation = OperationContext.model_validate(operation)
        control = self.controls.bind(operation)
        control.checkpoint()
        value = self._verify(selection, operation, operation, control)
        return self._publish_value(value, control)

    def _publish_value(
        self, value: InitialStateChecks, control: OperationControl
    ) -> EvidenceRef:
        raw = value.model_dump_json().encode()
        metadata = EvidenceMetadata(
            media_type="application/json",
            content_schema=value.schema_version,
            visibility="private",
            producer="initial-observation-checks-v1",
        )
        candidate = evidence_reference(raw, metadata)
        try:
            reference = EvidenceRef.model_validate(
                self.store.put(raw, metadata, control=control)
            )
        except BaseException as error:
            # A deterministic candidate is not proof of existence or a retry
            # permit. Keep the original exception and inspect exact bytes only.
            setattr(error, "initial_checks_candidate_reference", candidate)
            raise
        if (
            reference.sha256,
            reference.size_bytes,
            reference.media_type,
            reference.content_schema,
            reference.visibility,
            reference.producer,
        ) != (
            hashlib.sha256(raw).hexdigest(),
            len(raw),
            metadata.media_type,
            metadata.content_schema,
            metadata.visibility,
            metadata.producer,
        ):
            mismatch = EvidenceIntegrityError("Store changed initial-check publication")
            setattr(mismatch, "candidate_reference", reference)
            raise mismatch
        try:
            control.checkpoint()
        except Exception as error:
            raise StateCommitUnconfirmed(reference) from error
        return reference

    def load(
        self,
        selection: InitialObservationSelection,
        reference: EvidenceRef,
        operation: OperationContext,
    ) -> InitialStateChecks:
        selection = InitialObservationSelection.model_validate(selection)
        operation = OperationContext.model_validate(operation)
        control = self.controls.bind(operation)
        actual = self.reader.reads.parse(
            reference, "initial-state-checks/1", InitialStateChecks, control
        )
        if actual != self._verify(selection, actual.operation, operation, control):
            raise OwnershipConflict("Initial checks differ from original browser facts")
        control.checkpoint()
        return actual

    def publish_complete(
        self, selection: InitialObservationSelection, operation: OperationContext
    ) -> PublishedInitialObservation:
        """One graph for publication, exact readback and this caller's baseline.

        No body or permission is retained on this adapter. The original semantic
        and live authority runs before publication and again after exact readback.
        """
        selection = InitialObservationSelection.model_validate(selection)
        operation = OperationContext.model_validate(operation)
        control = self.controls.bind(operation)
        control.checkpoint()
        loaded = self.reader.load_complete(selection, operation, control)
        preparation = loaded.preparation
        if preparation is None:
            preparation = self.reader.reads.parse(
                selection.preparation.preparation_ref,
                "preparation-receipt/1",
                PreparationReceipt,
                control,
            )
        expected = self._verify_inputs(loaded.inputs, operation, operation, control)
        reference = self._publish_value(expected, control)
        try:
            actual = self.reader.reads.parse(
                reference, "initial-state-checks/1", InitialStateChecks, control
            )
            if actual != expected or actual != self._verify_inputs(
                loaded.inputs, operation, operation, control
            ):
                raise OwnershipConflict(
                    "Initial checks differ from original browser facts"
                )
            control.checkpoint()
        except Exception as error:
            raise StateCommitUnconfirmed(reference) from error
        return PublishedInitialObservation(
            reference, actual, loaded.inputs, preparation
        )

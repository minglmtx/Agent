"""Decode original retained source declarations; no inferred or replacement evidence."""

import json
from pathlib import Path
from lab_generate_skill.bootstrap.map_closed_source import ClosedMapSourceDeclarations
from lab_generate_skill.domain.baseline import BaselineInputs
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.initial_observation import InitialObservationSelection
from lab_generate_skill.domain.lifecycle import ResourceRecord
from lab_generate_skill.domain.map_initial_capture import MapInitialEvidence
from lab_generate_skill.domain.preparation_record import PreparedPublication
from lab_generate_skill.domain.resource_acquisition import ResourceAcquisitionIntent
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.ports.evidence import EvidenceStore
from lab_generate_skill.ports.lifecycle import OperationControl


def original_closed_source(
    path: Path, store: EvidenceStore, control: OperationControl
) -> ClosedMapSourceDeclarations:
    facts = json.loads(path.read_bytes())
    observed, qualified = facts["prepared_browser"], facts["qualified_source"]
    original = BaselineInputs.model_validate_json(
        store.read(EvidenceRef.model_validate(observed["baseline_inputs_ref"]), control)
    )
    browser_record = ResourceRecord.model_validate_json(
        json.dumps(observed["browser_record"])
    )
    acquisition = ResourceAcquisitionIntent.model_validate_json(
        store.read(browser_record.events[1].evidence[0], control)
    )
    refs = original.initial.checks.checks[0].evidence
    if len(refs) != 4:
        raise ValueError("Original navigation initial capture reference set required")
    return ClosedMapSourceDeclarations(
        context_ref=EvidenceRef.model_validate(qualified["context_receipt_ref"]),
        environment_ref=EvidenceRef.model_validate(
            qualified["environment_selection_ref"]
        ),
        reset_ref=EvidenceRef.model_validate(qualified["reset_selection_ref"]),
        initial=InitialObservationSelection(
            preparation=PreparedPublication.model_validate_json(
                json.dumps(observed["preparation_publication"])
            ),
            browser_spec_ref=acquisition.configuration_ref,
            browser_acquired_ref=EvidenceRef.model_validate(
                observed["browser_started_ref"]
            ),
        ),
        initial_capture=MapInitialEvidence(intent_ref=refs[2], result_ref=refs[3]),
        site=SiteResourceSpec.model_validate_json(json.dumps(facts["configuration"])),
        browser=BrowserResourceSpec.model_validate_json(
            json.dumps(observed["browser_spec"])
        ),
        site_record=ResourceRecord.model_validate_json(
            json.dumps(facts["resource_record"])
        ),
        browser_record=browser_record,
    )

"""Deterministic installed default-factory check; stdin contains metadata only."""

import importlib
import json
import sys
from lab_generate_skill.bootstrap.actor_deployment import accepted_actor_defaults
from lab_generate_skill.domain.actor_engine import ActorEngineConfig
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError


def main() -> None:
    payload = json.load(sys.stdin)
    config = ActorEngineConfig.model_validate_json(payload["config"])
    validation_ref = EvidenceRef.model_validate_json(payload["validation_ref"])
    software_ref = EvidenceRef.model_validate_json(payload["software_ref"])
    validation = payload["validation"].encode()
    software = payload["software"].encode()
    selected, parameters = accepted_actor_defaults(
        config, payload["inventory"], validation_ref, validation, software_ref, software
    )
    assert accepted_actor_defaults(
        selected,
        payload["inventory"],
        validation_ref,
        validation,
        software_ref,
        software,
    ) == (selected, parameters)
    try:
        accepted_actor_defaults(
            config,
            payload["inventory"],
            validation_ref,
            validation + b" ",
            software_ref,
            software,
        )
    except EvidenceIntegrityError:
        rejected = True
    else:
        raise AssertionError("Changed resource proof was accepted")
    module = importlib.import_module("lab_generate_skill.bootstrap.actor_deployment")
    assert module.__file__ is not None and "torch" not in sys.modules
    print(
        json.dumps(
            {
                "config": selected.model_dump(mode="json"),
                "parameters": parameters.model_dump(mode="json"),
                "module": module.__file__,
                "no_torch_import": True,
                "changed_proof_rejected": rejected,
            }
        )
    )


if __name__ == "__main__":
    main()

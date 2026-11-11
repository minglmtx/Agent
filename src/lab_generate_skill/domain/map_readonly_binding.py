"""Pure exact projection; no source receipt, owner or bytes are granted here."""

import hashlib
from .map_runtime_inputs import MapRuntimeInputs
from .map_readonly_inputs import MapReadonlyInputs


def bind_map_readonly_inputs(
    current: MapRuntimeInputs, source: MapRuntimeInputs
) -> MapRuntimeInputs:
    current, source = MapRuntimeInputs.model_validate(
        current
    ), MapRuntimeInputs.model_validate(source)
    if source.readonly_inputs is not None or current.readonly_inputs is not None:
        raise ValueError(
            "Readonly input handoff cannot chain or replace a prior binding"
        )
    projected = source.model_copy(update={"files": current.files})
    if projected != current:
        raise ValueError(
            "Readonly Map source differs in publication, images or complete inventories"
        )
    retained = MapReadonlyInputs(
        source_instance_id=source.files.instance_id,
        source_node_root=source.files.node_root,
        source_runtime_sha256=hashlib.sha256(
            source.model_dump_json().encode()
        ).hexdigest(),
    )
    return MapRuntimeInputs.model_validate(
        current.model_copy(
            update={
                "schema_version": "map-native-runtime-inputs/2",
                "readonly_inputs": retained,
            }
        )
    )

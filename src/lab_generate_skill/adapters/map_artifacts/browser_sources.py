"""Read all four frozen original frontend files under original browser authority."""

from pathlib import Path
from lab_generate_skill.domain.map_browser_inputs import MapBrowserInputs
from lab_generate_skill.ports.map_private_artifact import MapArtifactAuthority
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.map_runtime.metadata import read_pinned_bytes


class OriginalMapBrowserSources:
    def __init__(
        self, inputs: MapBrowserInputs, authority: MapArtifactAuthority
    ) -> None:
        self.inputs = MapBrowserInputs.model_validate(inputs)
        self.authority = authority

    def read(self, control: OperationControl) -> dict[str, bytes]:
        self.authority.verify(self.inputs.plan, "read", control)
        source = self.inputs.collection.original_sources
        result = {}
        for pin in source.files:
            path = Path(source.root) / pin.path
            leaf = pin.model_copy(update={"path": path.name})
            result[path.name] = read_pinned_bytes(path, leaf, control)
        self.authority.verify(self.inputs.plan, "read", control)
        return result

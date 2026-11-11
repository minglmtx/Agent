"""Original successful exchange storage. Never invokes a model or grants replay.

Publish requires independently captured command/reply CAS and original acquired
resource evidence. Concrete producer admission remains mandatory. Inspection
works after resource closure; missing evidence is unknown, never permission to
regenerate. Exact repeat confirms the original record, differing repeat fails.
"""

from typing import Protocol
from lab_generate_skill.domain.generator_execution import GeneratorExecutionRecord
from lab_generate_skill.domain.local_generator import (
    LocalGeneratorIntent,
    LocalGeneratorOutput,
)
from lab_generate_skill.ports.lifecycle import OperationControl


class GeneratorExecutions(Protocol):
    def publish(
        self, record: GeneratorExecutionRecord, control: OperationControl
    ) -> None: ...
    def load(
        self, intent: LocalGeneratorIntent, control: OperationControl
    ) -> GeneratorExecutionRecord: ...
    def output(
        self, record: GeneratorExecutionRecord, control: OperationControl
    ) -> LocalGeneratorOutput: ...

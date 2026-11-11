"""Local Generator inference with persisted completion, separate from paid sends.

An implementation must verify the registered construction intent, exact model,
sampling/input bindings, writer/claim and original request ownership BEFORE
inference. Persist intent first, reject uncertain/duplicate execution; an exact
known completion may be read back but must not invoke the model again. No implicit
retry or truncation. Freeze actual sampling parameters as model-parameters/1.
Persist canonical GeneratorTextCompletion as private generator-model-response/1
BEFORE returning its EvidenceRef. Invalid/length responses are still retained.
Use request.input_bytes() only as model messages, not the private envelope.
External supervision owns hard deadlines and model resource cleanup. There is
no default backend or permission implementation and no fabricated paid ledger.
"""

from typing import Protocol
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.generator_model import GeneratorModelRequest
from lab_generate_skill.domain.lifecycle import OperationContext


class GeneratorInference(Protocol):
    def generate(
        self, request: GeneratorModelRequest, op: OperationContext
    ) -> EvidenceRef: ...

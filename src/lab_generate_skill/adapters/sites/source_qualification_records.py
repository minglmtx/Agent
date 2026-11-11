"""Original live source definitions/preparation records, before execution claims.

These authorities verify the one producer's original immutable inputs and actual
acquired resource. Existing TaskBindings/PreparationRecords read dependencies
and recompute site checks. No site effect, model or execution grant is issued.
"""

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.preparation_record import PreparationInputs
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.state_checks import InitialStateSpec, StateChecks
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.site_handle import SiteHandle
from .source_qualification_native import SourceQualificationNativeAuthority


@dataclass(frozen=True)
class QualificationTaskDefinition:
    binding: TaskBinding
    public: PublicTask
    private: bytes
    spec: InitialStateSpec


@dataclass(frozen=True)
class QualificationPreparationFacts:
    request: SiteTaskRequest
    result: SiteTaskResult
    environment: EnvironmentBaseline


class SourceQualificationRecordAuthority:
    def __init__(
        self,
        native: SourceQualificationNativeAuthority,
        definition: QualificationTaskDefinition,
        site: SiteHandle,
        preparation: Callable[[], QualificationPreparationFacts | None],
    ) -> None:
        if (
            not isinstance(native, SourceQualificationNativeAuthority)
            or not isinstance(definition, QualificationTaskDefinition)
            or site is None
            or not callable(preparation)
        ):
            raise TypeError(
                "Original source native/resource/definition/preparation supplier required"
            )
        self.native, self.definition, self.site, self.preparation = (
            native,
            definition,
            site,
            preparation,
        )
        if (
            definition.binding.identity != native.owner.scope.task
            or definition.public.identity != native.owner.scope.task
            or definition.spec.task != native.owner.scope.task
            or type(definition.private) is not bytes
            or not definition.private
        ):
            raise OwnershipConflict(
                "Source records changed original complete task definition"
            )

    def verify_binding(
        self,
        binding: TaskBinding,
        public_task: PublicTask,
        private_spec: bytes,
        baseline: bytes,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self.native.require_acquired(op, control)
        d = self.definition
        public_origin, actual_origin = urlsplit(public_task.start_url), urlsplit(
            self.site.site.instance.endpoint
        )
        if (
            binding != d.binding
            or public_task != d.public
            or private_spec != d.private
            or baseline != d.spec.model_dump_json().encode()
            or self.site.site.instance.files != self.native.spec.configuration.files
            or (public_origin.scheme, public_origin.netloc)
            != (actual_origin.scheme, actual_origin.netloc)
        ):
            raise OwnershipConflict(
                "Source binding differs from original task bytes/actual origin"
            )
        self.native.owner.require_caller(op, control)

    def verify(
        self,
        inputs: PreparationInputs,
        checks: StateChecks,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self.native.require_acquired(op, control)
        expected = self.preparation()
        d = self.definition
        if (
            not isinstance(expected, QualificationPreparationFacts)
            or inputs.binding != d.binding
            or inputs.public_task != d.public
            or inputs.spec != d.spec
            or inputs.request != expected.request
            or inputs.result != expected.result
            or inputs.environment != expected.environment
            or expected.request.action != "prepare"
            or expected.result.request_sha256 != expected.request.digest
            or expected.environment.scope != self.native.owner.scope
            or expected.environment.checks.status != "pass"
            or checks.required != d.spec.preparation_checks
            or checks.status != "pass"
        ):
            raise OwnershipConflict(
                "Source preparation changed original measured inputs/checks"
            )
        self.native.owner.require_caller(op, control)

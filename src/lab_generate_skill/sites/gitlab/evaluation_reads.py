"""Concrete SSH contract/native facts over shared original readonly context joins."""

from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.gitlab_browser_initialization import (
    GitlabSshKeyInitialization,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError, EvidenceNotFound
from lab_generate_skill.ports.evidence import EvidenceReader
from lab_generate_skill.ports.lifecycle import OperationControl
from .evidence_schema import SshKeyEvidence, SshKeyFacts
from .state_reads import NativeStateLoader
from .tasks.ssh_key_environment import SshKeyEnvironmentChecks
from .tasks.ssh_key_spec import SshKeySpec
from .tasks.ssh_key_binding import NativeSshInputLoader
from .evaluation_capture import native_capture
from .evaluation_context import read_context, check_context, final_page


class SshKeyEvaluationReads:
    def __init__(
        self, native_loader: NativeStateLoader, input_loader: NativeSshInputLoader
    ) -> None:
        self.native_loader, self.input_loader = native_loader, input_loader

    def __call__(
        self,
        contract: EvaluationContract,
        selected: SshKeyEvidence,
        reader: EvidenceReader,
        control: OperationControl,
    ) -> SshKeyFacts:
        if (
            selected.environment_ref is None
            or selected.browser_spec_ref is None
            or selected.before is None
            or selected.after is None
            or selected.page is None
            or selected.trace_ref is None
        ):
            raise EvidenceNotFound(
                "Required original SSH capture/context/trace missing"
            )
        reads = SshKeyEnvironmentChecks(reader, self.native_loader)
        context = read_context(
            reads,
            contract,
            selected.environment_ref,
            selected.browser_spec_ref,
            selected.trace_ref,
            control,
        )
        spec = reads.read(
            contract.completion_spec_ref,
            "gitlab-profile-ssh-key/1",
            SshKeySpec,
            control,
        )
        if spec.task != contract.identity:
            raise EvidenceIntegrityError(
                "SSH evaluation changed original private identity"
            )
        native = reader.read(spec.native_contract_ref, control=control)
        if (
            self.input_loader(
                native, spec.native_contract_ref, context.public
            ).private_spec
            != spec
        ):
            raise EvidenceIntegrityError(
                "SSH evaluation changed original frozen contract"
            )
        env, trace = context.environment, context.trace
        _, site, snapshot = reads._environment(env, control)
        check_context(
            reads,
            contract,
            context,
            site,
            snapshot.native_before.context.instance.endpoint,
            "gitlab_profile_ssh_key",
            control,
        )
        before_intent, before = native_capture(
            reads,
            selected.before,
            contract,
            spec,
            site,
            snapshot,
            trace,
            env.snapshot_ref.sha256,
            control,
        )
        after_intent, after = native_capture(
            reads,
            selected.after,
            contract,
            spec,
            site,
            snapshot,
            trace,
            env.snapshot_ref.sha256,
            control,
        )
        first, last = before_intent.request.inspection, after_intent.request.inspection
        if (
            first.snapshot_ref != env.snapshot_ref
            or last.snapshot_ref != env.snapshot_ref
            or first.operation.operation_id == last.operation.operation_id
            or first.operation.recovery_ref != last.operation.recovery_ref
        ):
            raise EvidenceIntegrityError(
                "SSH evaluation lost original distinct before/after captures"
            )
        initialization = context.browser.configuration.initialization
        if (
            not isinstance(initialization, GitlabSshKeyInitialization)
            or initialization.native_account_id != before.account.id
        ):
            raise EvidenceIntegrityError(
                "SSH evaluation changed original native login account"
            )
        page = final_page(reads, context, selected.page, control)
        return SshKeyFacts(context.public, spec, before, after, page, trace)

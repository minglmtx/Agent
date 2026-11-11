"""Selected GitLab source preparation on current records and original authority."""

from lab_generate_skill.bootstrap.gitlab_ssh_records import (
    bind_ssh_key_records,
    ssh_key_preparation_records,
)
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.lifecycle import RecoveryPlan, OperationContext
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from site_resource_fixtures import Case
from site_preparation_native import NativePreparation
from gitlab_source_selection import GitlabSourceSelection
from lab_generate_skill.bootstrap.gitlab_group_records import (
    bind_group_records,
    group_preparation_records,
)


class GitlabPreparation(NativePreparation):
    attempt_id = "native-gitlab-attempt"
    context_id = "native-gitlab-context"

    def __init__(
        self,
        c: Case,
        endpoint: str,
        *,
        state_spec: InitialStateSpec,
        selection: GitlabSourceSelection,
        allowed_actions: tuple[str, ...] | None = None,
    ) -> None:
        if not isinstance(selection, GitlabSourceSelection):
            raise TypeError("Explicit validated GitLab selection required")
        selection.check_configuration(c.spec.configuration)
        if state_spec != selection.initial_spec:
            raise ValueError("Selected complete GitLab family state policy required")
        self.c = c
        self.request = None
        self.result = None
        self.environment = None
        self.selection = selection
        self.public = selection.public_at(endpoint, allowed_actions)
        if selection.group:
            self.attempt_id = "native-gitlab-group-attempt"
            self.context_id = "native-gitlab-group-context"
        native = self.raw(selection.native, "gitlab-native-contract/1")
        self.task_spec = selection.load(native, self.public)
        self.spec = state_spec
        self.spec_ref = self.put(state_spec)
        self.binding = TaskBinding(
            identity=self.public.identity,
            registration_id=(
                "engineering-gitlab-group"
                if selection.group
                else "engineering-gitlab-ssh"
            ),
            public_task_ref=self.put(self.public, "public"),
            private_spec_ref=self.put(self.task_spec),
            baseline_ref=self.spec_ref,
        )
        binding_factory = (
            bind_group_records if selection.group else bind_ssh_key_records
        )
        self.bindings = binding_factory(c.evidence, c.controls, self)
        self.binding_ref = self.bindings.publish(self.binding, c.op)
        self.recovery = RecoveryPlan(
            recovery_id="native-gitlab-recovery",
            owner=c.spec.token.owner,
            attempt_id=self.attempt_id,
            baseline_ref=self.spec_ref,
            restore_component_id=(
                "gitlab-group-creation" if selection.group else "gitlab-profile-ssh-key"
            ),
            restore_component_version="1",
            state_coverage=state_spec.task_reset_checks,
        )
        self.recovery_ref = self.put(self.recovery)
        preparation_factory = (
            group_preparation_records
            if selection.group
            else ssh_key_preparation_records
        )
        self.records = preparation_factory(c.evidence, c.controls, self.bindings, self)

    @property
    def native_contract_ref(self) -> EvidenceRef:
        return self.task_spec.native_contract_ref

    def private_input_json(self) -> str:
        return self.task_spec.model_dump_json()

    def verify_binding(
        self,
        binding: TaskBinding,
        public_task: PublicTask,
        private_spec: bytes,
        baseline: bytes,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        control.checkpoint()
        assert binding == self.binding and public_task == self.public
        assert (
            private_spec == self.private_input_json().encode()
            and baseline == self.spec.model_dump_json().encode()
        )

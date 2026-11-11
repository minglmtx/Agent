"""Selected Reddit source preparation on current records and original authority."""

from urllib.parse import urlsplit
from lab_generate_skill.bootstrap.reddit_native_image import load_image_inputs
from lab_generate_skill.bootstrap.reddit_image_records import (
    bind_image_records,
    image_preparation_records,
)
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.lifecycle import RecoveryPlan, OperationContext
from lab_generate_skill.domain.task import TaskBinding, PublicTask
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.reddit.tasks.image_policy import image_initial_spec
from site_resource_fixtures import Case
from site_preparation_native import NativePreparation
from test_reddit_image_inputs import FIXTURE, public_task
from lab_generate_skill.domain.reddit_image_start import image_start_path


class RedditPreparation(NativePreparation):
    attempt_id = "native-reddit-attempt"
    context_id = "native-reddit-context"

    def __init__(
        self,
        c: Case,
        endpoint: str,
        *,
        state_spec: InitialStateSpec,
        allowed_actions: tuple[str, ...] | None = None,
        native_input: bytes | None = None,
        public_input: PublicTask | None = None,
    ) -> None:
        if type(endpoint) is not str:
            raise TypeError("Original Reddit root endpoint required")
        origin = urlsplit(endpoint)
        if (
            origin.scheme != "http"
            or origin.hostname != "127.0.0.1"
            or origin.port is None
            or not 1024 <= origin.port <= 65535
            or endpoint != f"http://127.0.0.1:{origin.port}/"
        ):
            raise ValueError("Original Reddit root endpoint required")
        if (native_input is None) != (public_input is None):
            raise ValueError(
                "Selected native and public Reddit declarations must be paired"
            )
        if native_input is not None and type(native_input) is not bytes:
            raise TypeError("Selected Reddit native declaration must be bytes")
        original_public = (
            public_task()
            if public_input is None
            else PublicTask.model_validate(public_input)
        )
        if public_input is not None and public_input.start_url != endpoint.rstrip(
            "/"
        ) + image_start_path(public_input.identity):
            raise ValueError(
                "Selected public Reddit start differs from the original allocation"
            )
        self.c = c
        self.request = None
        self.result = None
        self.environment = None
        self.public = PublicTask.model_validate(
            {
                **original_public.model_dump(),
                "start_url": endpoint.rstrip("/")
                + image_start_path(original_public.identity),
                **(
                    {}
                    if allowed_actions is None
                    else {"allowed_actions": allowed_actions}
                ),
            }
        )
        if state_spec != image_initial_spec(self.public.identity):
            raise ValueError("Selected complete Reddit state policy required")
        raw = FIXTURE.read_bytes() if native_input is None else native_input
        native = self.raw(raw, "reddit-native-contract/1")
        self.image_spec = load_image_inputs(raw, native, self.public).private_spec
        self.spec = state_spec
        self.spec_ref = self.put(state_spec)
        self.binding = TaskBinding(
            identity=self.public.identity,
            registration_id="engineering-reddit-image",
            public_task_ref=self.put(self.public, "public"),
            private_spec_ref=self.put(self.image_spec),
            baseline_ref=self.spec_ref,
        )
        self.bindings = bind_image_records(c.evidence, c.controls, self)
        self.binding_ref = self.bindings.publish(self.binding, c.op)
        self.recovery = RecoveryPlan(
            recovery_id="native-reddit-recovery",
            owner=c.spec.token.owner,
            attempt_id=self.attempt_id,
            baseline_ref=self.spec_ref,
            restore_component_id="reddit-native-image",
            restore_component_version="1",
            state_coverage=state_spec.task_reset_checks,
        )
        self.recovery_ref = self.put(self.recovery)
        self.records = image_preparation_records(
            c.evidence, c.controls, self.bindings, self
        )

    @property
    def native_contract_ref(self) -> EvidenceRef:
        return self.image_spec.native_contract_ref

    def private_input_json(self) -> str:
        return self.image_spec.model_dump_json()

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

"""Selected original Shopping input, with explicit engineering-only admission.

Reuse original publication and retained-resource authority; no formal source or
training rights are created by this fixture.
"""

from urllib.parse import urlsplit
from lab_generate_skill.bootstrap.shopping_order_eta import load_order_eta_inputs
from lab_generate_skill.bootstrap.shopping_order_eta_records import (
    bind_order_eta_records,
)
from lab_generate_skill.bootstrap.shopping_preparation import (
    shopping_preparation_records,
)
from lab_generate_skill.domain.state_checks import InitialStateSpec
from lab_generate_skill.domain.lifecycle import RecoveryPlan
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.sites.shopping.tasks.order_eta_state import (
    OrderEtaExecutionInput,
)
from site_resource_fixtures import Case
from site_preparation_native import NativePreparation
from test_shopping_order_eta_inputs import FIXTURE, public_task


class ShoppingPreparation(NativePreparation):
    attempt_id = "native-shopping-attempt"
    context_id = "native-shopping-context"

    def __init__(
        self,
        c: Case,
        endpoint: str,
        *,
        state_spec: InitialStateSpec,
        allowed_actions: tuple[str, ...] | None = None,
    ) -> None:
        self.c = c
        self.request = None
        self.result = None
        self.environment = None
        raw = FIXTURE.read_bytes()
        original = self.raw(raw, "shopping-native-contract/1")
        origin = urlsplit(endpoint)
        assert origin.path == "/" and not origin.query and not origin.fragment
        self.public = public_task(
            start_url=origin._replace(path="/customer/account/").geturl(),
            **({} if allowed_actions is None else {"allowed_actions": allowed_actions}),
        )
        self.data = OrderEtaExecutionInput(
            spec=load_order_eta_inputs(raw, original, self.public).private_spec
        )
        self.spec = state_spec
        assert self.spec.task == self.public.identity
        self.spec_ref = self.put(self.spec)
        self.binding = TaskBinding(
            identity=self.public.identity,
            registration_id="engineering-shopping-eta",
            public_task_ref=self.put(self.public, "public"),
            private_spec_ref=self.put(self.data.spec),
            baseline_ref=self.spec_ref,
        )
        self.bindings = bind_order_eta_records(c.evidence, c.controls, self)
        self.binding_ref = self.bindings.publish(self.binding, c.op)
        self.recovery = RecoveryPlan(
            recovery_id="native-shopping-recovery",
            owner=c.spec.token.owner,
            attempt_id=self.attempt_id,
            baseline_ref=self.spec_ref,
            restore_component_id="shopping-order-eta",
            restore_component_version="1",
            state_coverage=self.spec.task_reset_checks,
        )
        self.recovery_ref = self.put(self.recovery)
        self.records = shopping_preparation_records(
            c.evidence, c.controls, self.bindings, self
        )

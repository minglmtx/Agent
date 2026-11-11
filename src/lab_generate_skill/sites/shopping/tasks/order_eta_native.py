"""Fixed native initialization/read on the original Shopping instance, no replay."""

import json
from collections.abc import Callable
from lab_generate_skill.ports.lifecycle import OperationControl
from ..instance import ShoppingInstance
from ..query_capture import capture_query_protection
from ..query_state import QueryProtectedState
from ..service_commands import container
from .order_eta_spec import OrderEtaSpec
from .order_eta_state import NativeEtaFixture, OrderEtaState
from .order_eta_programs import RECORDED_ETA

SHOPPING_IMAGE_SHA = "455ec7d98aa89b7b63b627aea567f91816d75da50bd160f5db2cc1dfe52f6812"


class OrderEtaNative:
    def __init__(
        self, instance: ShoppingInstance, customer: Callable[[OperationControl], str]
    ) -> None:
        self.instance, self.customer = instance, customer
        self.initialization_attempted = False

    def protected(self, control: OperationControl) -> QueryProtectedState:
        instance = self.instance
        if (
            instance.spec is None
            or instance.static_provenance is None
            or instance.state not in ("ready", "snapshotted", "resumed")
            or instance.spec.files.image.sha256 != SHOPPING_IMAGE_SHA
        ):
            raise RuntimeError("Original ready pinned Shopping instance required")
        instance.generations[-1].services.require_running()
        return capture_query_protection(
            instance.spec, instance.static_provenance, instance.commands, control
        )

    def observe(
        self, spec: OrderEtaSpec, control: OperationControl, *, initialize: bool = False
    ) -> OrderEtaState:
        spec = OrderEtaSpec.model_validate(spec)
        instance = self.instance
        if (
            instance.spec is None
            or instance.state != "snapshotted"
            or instance.spec.files.image.sha256 != SHOPPING_IMAGE_SHA
            or type(initialize) is not bool
            or (initialize and self.initialization_attempted)
            or (not initialize and not self.initialization_attempted)
        ):
            raise RuntimeError(
                "One snapshotted original native ETA initialization required"
            )
        instance.generations[-1].services.require_running()
        control.checkpoint()
        email = self.customer(control)
        if (
            type(email) is not str
            or not email
            or "@" not in email
            or any(c in email for c in ("\0", "\n", "\r"))
        ):
            raise ValueError("Original native customer identity unavailable")
        if initialize:
            self.initialization_attempted = True
        args = json.dumps(
            {
                "email": email,
                "order_number": spec.order_number,
                "date": spec.recorded_date,
                "operation": "initialize" if initialize else "read",
            }
        )
        raw = instance.commands.run(
            container(instance.spec) + ("php", "-r", RECORDED_ETA, args), control
        )
        fixture = NativeEtaFixture.model_validate_json(raw)
        state = OrderEtaState(
            task=spec.task, fixture=fixture, protected=self.protected(control)
        )
        state.check(spec)
        control.checkpoint()
        return state

"""Create the declared product once; inspect original record without reinitializing.

This is a supervised private-worker primitive, not TaskFamily/PreparedTask or
initial observation. Caller owns persistent intent, quiescence, fixture authority
and complete reset. Any effectful failure leaves the instance for reconciliation.
"""

import json
from typing import Literal
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from ..service_contract import AdminServiceSpec
from ..service_commands import container
from .product_description_spec import ProductDescriptionSpec
from .product_seed_contract import ProductSeed, ProductState
from .product_seed_program import PRODUCT_SEED_PHP
from .product_seed_validation import (
    validate_product_fixture,
    validate_product_initial_state,
)


class ProductStateReplyError(ValueError):
    def __init__(self, raw_reply: bytes) -> None:
        self.raw_reply = raw_reply
        super().__init__(
            "Invalid original product state reply; retain partial instance"
        )


class AdminProductSeed:
    def __init__(
        self,
        service: AdminServiceSpec,
        task: ProductDescriptionSpec,
        seed: ProductSeed,
        commands: NativeCommands,
    ) -> None:
        self.service = AdminServiceSpec.model_validate(service)
        self.task = ProductDescriptionSpec.model_validate(task)
        self.seed = ProductSeed.model_validate(seed)
        self.commands = commands
        validate_product_fixture(self.task, self.seed)
        self.attempted = False

    def _call(
        self, operation: Literal["initialize", "inspect"], control: OperationControl
    ) -> ProductState:
        control.checkpoint()
        payload: dict[str, object] = dict(
            operation=operation, product_id=self.task.product_id
        )
        if operation == "initialize":
            payload["values"] = self.seed.scenario.products[0].model_dump(mode="json")
        raw = self.commands.run(
            container(self.service)
            + (
                "php",
                "-r",
                PRODUCT_SEED_PHP,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            ),
            control,
        )
        try:
            result = ProductState.model_validate_json(raw)
            if (
                raw != result.model_dump_json().encode()
                or result.product_id != self.task.product_id
            ):
                raise ValueError(
                    "Product reply differs from original ID or canonical protocol"
                )
            return result
        except (ValueError, TypeError) as error:
            raise ProductStateReplyError(raw) from error

    def initialize(self, control: OperationControl) -> ProductState:
        if self.attempted:
            raise RuntimeError("Product initialization already attempted; inspect only")
        control.checkpoint()
        self.attempted = True
        result = self._call("initialize", control)
        validate_product_initial_state(self.task, self.seed, result)
        control.checkpoint()
        return result

    def inspect(self, control: OperationControl) -> ProductState:
        return self._call("inspect", control)

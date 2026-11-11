"""Category preparation measures unchanged full native protection; no SQL writes."""

from lab_generate_skill.ports.lifecycle import OperationControl
from ..instance import ShoppingInstance
from ..query_capture import capture_query_protection
from ..query_state import QueryProtectedState
from .order_eta_native import SHOPPING_IMAGE_SHA
from .navigation_spec import CategoryNavigationSpec
from .navigation_state import CategoryNavigationState


class CategoryNavigationNative:
    def __init__(self, instance: ShoppingInstance) -> None:
        self.instance = instance
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
        self,
        spec: CategoryNavigationSpec,
        control: OperationControl,
        *,
        initialize: bool = False,
    ) -> CategoryNavigationState:
        spec = CategoryNavigationSpec.model_validate(spec)
        if (
            self.instance.state != "snapshotted"
            or type(initialize) is not bool
            or (initialize and self.initialization_attempted)
            or (not initialize and not self.initialization_attempted)
        ):
            raise RuntimeError("One original snapshotted category preparation required")
        control.checkpoint()
        if initialize:
            # Once even if a subsequent native measurement fails or is cancelled.
            self.initialization_attempted = True
        state = CategoryNavigationState(
            task=spec.task, protected=self.protected(control)
        )
        state.check(spec)
        control.checkpoint()
        return state

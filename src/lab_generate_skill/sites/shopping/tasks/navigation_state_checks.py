"""Category environment/full Reset on the original Shopping proof algorithms."""

from lab_generate_skill.domain.identity import TaskIdentity
from .order_eta_state_checks import OrderEtaStateChecks
from .state_codec import ShoppingTaskStateCodec


class CategoryNavigationStateChecks(OrderEtaStateChecks):
    def task_codec(self, task: TaskIdentity) -> ShoppingTaskStateCodec:
        return ShoppingTaskStateCodec(task, "page_navigation")

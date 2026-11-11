"""One declared BrowserGym call with literal arguments; never evaluates code."""

import ast
from .browser import BrowserAction
from .task import PublicTask

PROTOCOL = "browsergym-highlevel-v1"


def validate_action(action: BrowserAction, task: PublicTask) -> None:
    action = BrowserAction.model_validate(action)
    task = PublicTask.model_validate(task)
    if action.protocol_id != PROTOCOL or action.name not in task.allowed_actions:
        raise ValueError("Browser action protocol/name is not allowed")
    tree = ast.parse(action.payload, mode="eval").body
    if (
        not isinstance(tree, ast.Call)
        or not isinstance(tree.func, ast.Name)
        or tree.func.id != action.name
    ):
        raise ValueError(
            "Browser action must contain exactly its declared function call"
        )
    for value in [*tree.args, *[k.value for k in tree.keywords]]:
        ast.literal_eval(value)
    if any(k.arg is None for k in tree.keywords) or len(
        {k.arg for k in tree.keywords}
    ) != len(tree.keywords):
        raise ValueError("Expanded or duplicate action keywords are forbidden")

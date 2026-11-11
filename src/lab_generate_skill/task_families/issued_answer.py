"""Read the literal text of an actual successful chat action; never execute it."""

import ast
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserReadout
from lab_generate_skill.domain.browser_action_protocol import validate_action
from lab_generate_skill.domain.task import PublicTask


def issued_message(
    action: BrowserAction, returned: BrowserReadout, task: PublicTask
) -> str | None:
    if returned.schema_version != "browser-step-return/1" or returned.action != action:
        raise ValueError("Answer requires its original actual browser return")
    validate_action(action, task)
    if action.name != "send_msg_to_user" or returned.observation.last_action_error:
        return None
    tree = ast.parse(action.payload, mode="eval").body
    assert isinstance(tree, ast.Call)
    if len(tree.args) == 1 and not tree.keywords:
        value = ast.literal_eval(tree.args[0])
    elif not tree.args and len(tree.keywords) == 1 and tree.keywords[0].arg == "text":
        value = ast.literal_eval(tree.keywords[0].value)
    else:
        return None
    return value if type(value) is str else None

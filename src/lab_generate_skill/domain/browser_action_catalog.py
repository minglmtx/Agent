"""The current public BrowserGym signatures, shared by role projections.

This catalog describes registered operations, never grants a task permission.
The original action grammar and task allow-list remain the execution gate.
"""

ACTOR_OBSERVATION_MODE = "current_page_full_ax"

ACTIONS = {
    "click": "click(bid)",
    "dblclick": "dblclick(bid)",
    "fill": "fill(bid, value)",
    "select_option": "select_option(bid, options)",
    "scroll": "scroll(delta_x, delta_y)",
    "press": "press(bid, key_comb)",
    "hover": "hover(bid)",
    "focus": "focus(bid)",
    "clear": "clear(bid)",
    "drag_and_drop": "drag_and_drop(from_bid, to_bid)",
    "upload_file": "upload_file(bid, file_or_list)",
    "goto": "goto(url)",
    "go_back": "go_back()",
    "go_forward": "go_forward()",
    "new_tab": "new_tab()",
    "tab_focus": "tab_focus(index)",
    "tab_close": "tab_close()",
    "noop": "noop()",
    "send_msg_to_user": "send_msg_to_user(text)",
    "report_infeasible": "report_infeasible(reason)",
}


def declared_signatures(names: tuple[str, ...]) -> tuple[str, ...]:
    """Reject invented tools before either role builds a model request."""
    if (
        type(names) is not tuple
        or not names
        or any(type(name) is not str or name not in ACTIONS for name in names)
        or len(set(names)) != len(names)
    ):
        raise ValueError("Distinct registered browser action names required")
    return tuple(ACTIONS[name] for name in names)

"""Only original successful send_msg_to_user text counts as an issued answer."""

import pytest
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_action_protocol import PROTOCOL
from lab_generate_skill.task_families.issued_answer import issued_message
from browser_worker_fixtures import case
from browsergym_fixtures import operation
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "payload,expected",
    [
        ("send_msg_to_user('actual answer')", "actual answer"),
        ("send_msg_to_user(text='actual answer')", "actual answer"),
        ("send_msg_to_user(123)", None),
        ("send_msg_to_user(message='unsupported')", None),
        ("send_msg_to_user('one','two')", None),
    ],
)
def test_actual_return_literal_text_and_no_coercion(
    payload: str, expected: str | None
) -> None:
    _, service, _, client = case()
    try:
        client.start(operation(client.spec, "start"), control=guard())
        action = BrowserAction(
            action_id="issued",
            protocol_id=PROTOCOL,
            name="send_msg_to_user",
            payload=payload,
        )
        result = client.step(action, operation(client.spec, "message"), control=guard())
        assert issued_message(action, result, client.spec.task) == expected
        failed = result.model_copy(
            update={
                "observation": result.observation.model_copy(
                    update={"last_action_error": "original browser error"}
                ),
                "protocol_terminal": True,
            }
        )
        assert issued_message(action, failed, client.spec.task) is None
        with pytest.raises(ValueError):
            issued_message(
                action.model_copy(update={"action_id": "other"}),
                result,
                client.spec.task,
            )
    finally:
        service.close()

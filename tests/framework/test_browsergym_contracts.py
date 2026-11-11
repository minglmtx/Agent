"""Browser protocol/capture preflight; no Chromium needed for these boundaries."""

import ast
from pathlib import Path
from typing import Any
import pytest
from pydantic import ValidationError
from lab_generate_skill.adapters.browsergym.actions import (
    validate_action,
    PROTOCOL,
    action_set,
    map_action,
)
from lab_generate_skill.adapters.browsergym.events import BrowserEvents
from lab_generate_skill.adapters.browsergym.native_controls import (
    NATIVE_CHECKBOX_CLICK,
    NATIVE_CATEGORY_POSITION_FILL,
)
from lab_generate_skill.domain.browser import BrowserAction
from lab_generate_skill.domain.browser_session import BrowserSessionSpec
from browsergym_fixtures import spec


@pytest.mark.parametrize("payload", ["fill('a', 'text')", 'fill(bid="a", value="")'])
def test_exact_literal_action_accepted(payload: str) -> None:
    validate_action(
        BrowserAction(
            action_id="one", protocol_id=PROTOCOL, name="fill", payload=payload
        ),
        spec().task,
    )


@pytest.mark.parametrize(
    "payload",
    [
        "fill('a', str(1))",
        "click('a')",
        "page.fill('a','x')",
        "fill(*['a','x'])",
        "fill(**{'bid':'a'})",
        "fill('a','x');click('b')",
        "fill(value='x',value='y')",
    ],
)
def test_ambiguous_or_executable_arguments_rejected(payload: str) -> None:
    with pytest.raises((ValueError, SyntaxError)):
        validate_action(
            BrowserAction(
                action_id="one", protocol_id=PROTOCOL, name="fill", payload=payload
            ),
            spec().task,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("seed", True),
        ("seed", -1),
        ("action_timeout_ms", 499),
        ("action_timeout_ms", 10001),
        ("max_events", 3),
        ("max_events", 4097),
        ("chromium_executable", "relative"),
        ("schema_version", "old"),
    ],
)
def test_session_invalid_config_rejected(field: str, value: object) -> None:
    data = spec().model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        BrowserSessionSpec.model_validate(data)


def test_unsupported_capture_never_silently_downgrades() -> None:
    data = spec().model_dump()
    data["requirements"]["events"] = ("download",)
    with pytest.raises(ValidationError):
        BrowserSessionSpec.model_validate(data)


def test_event_overflow_is_retained_and_callback_errors_not_swallowed() -> None:
    events = BrowserEvents(1)
    events.add("before_navigation", url="http://127.0.0.1/")

    class Response:
        url = "http://127.0.0.1/"
        status = 200

    events.response(Response())
    assert len(events.events) == 1
    with pytest.raises(RuntimeError, match="capacity"):
        events.check()
    with pytest.raises(RuntimeError):
        events.add("terminal")


def test_response_is_not_falsely_linked_to_current_action() -> None:
    events = BrowserEvents(8)

    class Response:
        url = "http://127.0.0.1/"
        status = 200

    events.add("before_action", action_id="one")
    events.response(Response())
    events.add("after_action", action_id="one")
    assert [e.sequence for e in events.events] == [0, 1, 2]
    assert events.events[1].action_id is None


def test_native_mapping_preserves_original_function_bodies() -> None:
    project = Path(__file__).resolve().parents[2]
    old = ast.parse(
        (project / "src/lab_generate_skill/native_control_adapter.py").read_text()
    )
    originals = {n.name: n for n in old.body if isinstance(n, ast.FunctionDef)}
    for source in (NATIVE_CHECKBOX_CLICK, NATIVE_CATEGORY_POSITION_FILL):
        node = ast.parse(source).body[0]
        assert isinstance(node, ast.FunctionDef)
        assert ast.dump(node) == ast.dump(originals[node.name])
        compile(source, node.name, "exec")
    actions = action_set(1200)
    for payload in ("fill('a','text')", "click('a')", "send_msg_to_user('done')"):
        code = map_action(actions, payload, 1200)
        compile(code, "mapped-browser-action", "exec")
        assert payload.split("(")[0] in code


def test_public_projection_keeps_original_pure_logic() -> None:
    project = Path(__file__).resolve().parents[2] / "src/lab_generate_skill"

    class RemoveTypes(ast.NodeTransformer):
        def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST | None:
            return (
                ast.Assign(targets=[node.target], value=node.value)
                if node.value is not None
                else None
            )

        def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
            self.generic_visit(node)
            node.returns = None
            for arg in node.args.args:
                arg.annotation = None
            node.body = [
                item
                for item in node.body
                if not isinstance(item, ast.AnnAssign) or item.value is not None
            ]
            return node

    for oldname, newname in (
        ("ax_observation.py", "ax_native.py"),
        ("ax_observation.py", "ax_inline.py"),
        ("ax_observation.py", "ax_drag.py"),
        ("ax_observation.py", "ax_options.py"),
        ("public_control_state.py", "control_projection.py"),
    ):
        old = ast.parse((project / oldname).read_text())
        new = ast.parse((project / "adapters/browsergym" / newname).read_text())
        originals = {n.name: n for n in old.body if isinstance(n, ast.FunctionDef)}
        for node in new.body:
            if isinstance(node, ast.FunctionDef):
                assert ast.dump(RemoveTypes().visit(node)) == ast.dump(
                    originals[node.name]
                )


def test_unsupported_action_surface_rejected_before_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import browsergym.core as core  # type: ignore[import-untyped]
    from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
    from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
    from lab_generate_skill.adapters.clock import SystemClock
    from browsergym_fixtures import LoopbackAuthority, operation
    from test_slurm_commands import guard

    value = spec()
    value = value.model_copy(
        update={
            "task": value.task.model_copy(update={"allowed_actions": ("unsupported",)})
        }
    )

    def forbidden() -> None:
        pytest.fail("Unsupported action must not create a Playwright driver")

    monkeypatch.setattr(core, "_get_global_playwright", forbidden)
    engine = BrowserGymEngine(
        value, LoopbackAuthority(), SystemClock(), NavigatePublicTask()
    )
    with pytest.raises(ValueError, match="unsupported"):
        engine.start(operation(value, "start"), control=guard(10))
    assert engine.driver is None and engine.env is None


def test_observation_failure_retains_obtained_native_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lab_generate_skill.adapters.browsergym.engine import BrowserGymEngine
    from lab_generate_skill.adapters.browsergym.initialization import NavigatePublicTask
    from lab_generate_skill.adapters.clock import SystemClock
    from browsergym_fixtures import LoopbackAuthority, operation
    from test_slurm_commands import guard

    raw = {"captured": "original browser return"}

    class Env:
        def step(
            self, payload: str
        ) -> tuple[dict[str, str], float, bool, bool, dict[str, str]]:
            return raw, 0.0, False, False, {}

    engine = BrowserGymEngine(
        spec(), LoopbackAuthority(), SystemClock(), NavigatePublicTask()
    )
    engine.state = "ready"
    engine.env = Env()

    def broken(*args: object, **kwargs: object) -> None:
        raise ValueError("invalid original observation")

    monkeypatch.setattr(engine, "_readout", broken)
    action = BrowserAction(
        action_id="one", protocol_id=PROTOCOL, name="fill", payload="fill('a','x')"
    )
    with pytest.raises(ValueError, match="observation"):
        engine.step(action, operation(engine.spec, "one"), control=guard(30))
    assert engine.last_native_return is not None and engine.last_native_return[0] is raw
    assert getattr(engine, "state") == "quarantined" and engine.last_readout is None

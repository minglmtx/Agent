"""Strict single BrowserGym action, preserving native control mappings."""

import ast
from typing import Any
from lab_generate_skill.domain.browser_action_protocol import (
    PROTOCOL as PROTOCOL,
    validate_action as validate_action,
)
from .native_controls import NATIVE_CHECKBOX_CLICK, NATIVE_CATEGORY_POSITION_FILL


def action_set(milliseconds: int) -> Any:
    from browsergym.core.action.highlevel import HighLevelActionSet  # type: ignore[import-untyped]

    actions = HighLevelActionSet(
        subsets=["chat", "bid", "infeas", "nav", "tab"],
        strict=True,
        multiaction=False,
        retry_with_force=False,
    )

    class Timeout(ast.NodeTransformer):
        count = 0

        def visit_Call(self, node: ast.Call) -> ast.AST:
            self.generic_visit(node)
            if isinstance(node.func, ast.Attribute) and node.func.attr in (
                "click",
                "dblclick",
                "fill",
                "clear",
                "hover",
                "select_option",
                "check",
                "uncheck",
                "press",
                "focus",
            ):
                for kw in node.keywords:
                    if (
                        kw.arg == "timeout"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value == 500
                    ):
                        kw.value = ast.Constant(milliseconds)
                        self.count += 1
            return node

    update = Timeout()
    tree = update.visit(ast.parse(actions.python_includes))
    if not update.count:
        raise ValueError("Pinned BrowserGym action timeout API changed")
    actions.python_includes = ast.unparse(ast.fix_missing_locations(tree)) + "\n"
    return actions


def map_action(actions: Any, payload: str, milliseconds: int) -> str:
    code: str = actions.to_python_code(payload)
    node = ast.parse(code).body[-1]
    if (
        not isinstance(node, ast.Expr)
        or not isinstance(node.value, ast.Call)
        or not isinstance(node.value.func, ast.Name)
    ):
        raise ValueError("BrowserGym did not produce a single final action")
    name = node.value.func.id
    if name not in ("click", "fill"):
        return code
    prefix = "\n".join(code.splitlines()[: node.lineno - 1]) + "\n"
    source = NATIVE_CHECKBOX_CLICK if name == "click" else NATIVE_CATEGORY_POSITION_FILL
    source = source.replace("timeout=500)", f"timeout={milliseconds})")
    alias = (
        "click = native_checkbox_click"
        if name == "click"
        else "fill = native_category_position_fill"
    )
    return (
        prefix
        + ("original_browsergym_fill = fill\n" if name == "fill" else "")
        + source
        + "\n"
        + alias
        + "\n"
        + ast.unparse(node)
        + "\n"
    )

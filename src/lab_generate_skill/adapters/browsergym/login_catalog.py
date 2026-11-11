"""Read only the frozen benchmark login literal, without importing env globals.

The whole 1417-byte source is pinned. No code execution, environment fallback,
credential publication or password file is performed. Runtime source ownership
and the enclosing worker deadline remain the launcher's responsibility.
"""

import ast
import hashlib
from pathlib import Path
from typing import Literal
from lab_generate_skill.ports.lifecycle import OperationControl

CATALOG = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/tools/python-releases/lab-skill-20261025-v2/lib/python3.11/site-packages/webarena/browser_env/env_config.py"
)
CATALOG_SHA256 = "fcec91a2dafd5db16bb390ac5a6fd930ef59c6ef54445b85f7625d8f9404abd7"


def _login(
    site: Literal["shopping_admin", "shopping", "gitlab", "reddit"],
    control: OperationControl,
) -> tuple[str, str]:
    control.checkpoint()
    if site not in ("shopping_admin", "shopping", "gitlab", "reddit"):
        raise ValueError("Unsupported fixed benchmark login selection")
    if CATALOG.is_symlink() or not CATALOG.is_file():
        raise ValueError("Frozen benchmark login source unavailable")
    with CATALOG.open("rb") as stream:
        raw = stream.read(16385)
    if len(raw) > 16384 or hashlib.sha256(raw).hexdigest() != CATALOG_SHA256:
        raise ValueError("Frozen benchmark login source differs")
    assignments = [
        n
        for n in ast.parse(raw).body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "ACCOUNTS" for t in n.targets)
    ]
    if len(assignments) != 1:
        raise ValueError("One frozen login catalog required")
    accounts = ast.literal_eval(assignments[0].value)
    value = accounts[site]
    if (
        type(value) is not dict
        or set(value) != {"username", "password"}
        or any(type(x) is not str or not x or "\0" in x for x in value.values())
    ):
        raise ValueError("Unsupported benchmark login catalog")
    control.checkpoint()
    return value["username"], value["password"]


def admin_login(control: OperationControl) -> tuple[str, str]:
    return _login("shopping_admin", control)


def shopping_login(control: OperationControl) -> tuple[str, str]:
    return _login("shopping", control)


def gitlab_login(control: OperationControl) -> tuple[str, str]:
    return _login("gitlab", control)


def reddit_login(control: OperationControl) -> tuple[str, str]:
    return _login("reddit", control)

"""Compare parser diagnostics without treating an AST address as semantics.

Raw recorded failures remain immutable. Only the standard ValueError AST repr
has a process-local address; type, line, node class and all other text must match.
"""

import ast
import re

REJECTION_PREFIX = "proposal_rejected; executed=false; no action or observation read was executed; this is not a search result. "

_AST_ERROR = re.compile(
    r"malformed node or string(?: on line ([1-9][0-9]*))?: "
    r"<ast\.([A-Za-z][A-Za-z0-9_]*) object at 0x[0-9a-f]+>"
)


def same_parse_failure(error_type: str, message: str, error: BaseException) -> bool:
    if type(error_type) is not str or type(message) is not str:
        return False
    if error_type != type(error).__name__:
        return False
    actual = str(error)
    if message == actual:
        return True
    if type(error) is not ValueError:
        return False
    recorded, reproduced = _AST_ERROR.fullmatch(message), _AST_ERROR.fullmatch(actual)
    if (
        recorded is None
        or reproduced is None
        or recorded.groups() != reproduced.groups()
    ):
        return False
    node_type = getattr(ast, recorded.group(2), None)
    return isinstance(node_type, type) and issubclass(node_type, ast.AST)

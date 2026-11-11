"""Pure temporary-name derivation for an already admitted storage exchange.

The name is reconstructable from the durable intent; it is not permission to
unlink anything. Independent recovery must first verify the original worker,
root, binding and ownership. A collision must fail without touching that file.
"""

import hashlib
from pydantic import TypeAdapter
from lab_generate_skill.domain.validation import Identifier

_IDENTIFIER = TypeAdapter(Identifier)


def exchange_temporary_name(exchange_id: str) -> str:
    value = _IDENTIFIER.validate_python(exchange_id, strict=True)
    return ".pending-exchange-" + hashlib.sha256(value.encode("ascii")).hexdigest()

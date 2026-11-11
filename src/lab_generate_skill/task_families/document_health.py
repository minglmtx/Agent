"""Original native document-error predicate, shared without browser dependencies."""

import re


def is_error_document(url: str, status: object, title: str | None) -> bool:
    if url.startswith(("chrome-error:", "about:neterror")):
        return True
    if type(status) is int and status >= 400:
        return True
    normalized = " ".join((title or "").casefold().split())
    return bool(
        re.fullmatch(
            r"(?:404(?::| -)?\s*)?(?:page not found|not found|page you requested was not found|whoops, our bad\.\.\.)"
            r"(?:\s*[·|]\s*(?:gitlab|openstreetmap|one stop market))?",
            normalized,
        )
    )

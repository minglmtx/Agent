"""Compare native HTML form body values without changing textual content.

Only the observed LF/CRLF transport difference is equivalent. Spaces, case,
Markdown, lone CRs, missing lines and added text remain significant.
"""

def same_form_body(actual, expected):
    if not isinstance(actual, str) or not isinstance(expected, str):
        return False
    return actual.replace("\r\n", "\n") == expected.replace("\r\n", "\n")

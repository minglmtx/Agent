"""Selected supplied-key mutation and full unrelated-state preservation rules."""

import base64
import hashlib
import re
from urllib.parse import urlsplit
from ..evidence_schema import (
    GitlabPageHealth,
    CHECKS as CHECKS,
    SshKeyOutcome as SshKeyOutcome,
)
from .ssh_key_parameters import canonical_public_key
from .ssh_key_spec import SshKeySpec
from .ssh_key_state import SshKeyNativeState, AUTH_COLUMNS


def preserved(before: SshKeyNativeState, after: SshKeyNativeState) -> bool:
    if (
        before.account != after.account
        or before.refs != after.refs
        or before.guard != after.guard
    ):
        return False
    if (
        before.users.columns != after.users.columns
        or before.keys.columns != after.keys.columns
    ):
        return False
    old_users = {row["id"]: row for row in before.users.rows}
    new_users = {row["id"]: row for row in after.users.rows}
    if set(old_users) != set(new_users):
        return False
    for ident, row in old_users.items():
        ignored = set(AUTH_COLUMNS) if ident == before.account.id else set()
        if {k: v for k, v in row.items() if k not in ignored} != {
            k: v for k, v in new_users[ident].items() if k not in ignored
        }:
            return False
    old_keys = {row["id"]: row for row in before.keys.rows}
    new_keys = {row["id"]: row for row in after.keys.rows}
    return (
        set(old_keys) <= set(new_keys)
        and len(new_keys) - len(old_keys) <= 1
        and all(new_keys[ident] == row for ident, row in old_keys.items())
    )


def fingerprints(key: str, sha: object, md5: object) -> bool:
    wire = base64.b64decode(canonical_public_key(key).split()[1], validate=True)
    expected = "SHA256:" + base64.b64encode(
        hashlib.sha256(wire).digest()
    ).decode().rstrip("=")
    if sha is None:
        sha_ok = True
    elif isinstance(sha, str) and sha.startswith("\\x"):
        sha_ok = (
            re.fullmatch(r"\\x[0-9a-fA-F]{64}", sha) is not None
            and bytes.fromhex(sha[2:]) == hashlib.sha256(wire).digest()
        )
    else:
        sha_ok = sha in (expected, expected.removeprefix("SHA256:"))
    digest = hashlib.md5(wire).hexdigest()
    legacy = ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))
    return sha_ok and (md5 is None or md5 in (digest, legacy))


def decide_ssh_key(
    spec: SshKeySpec,
    before: SshKeyNativeState | None,
    after: SshKeyNativeState | None,
    page: GitlabPageHealth | None,
    *,
    site_origin: str,
    runtime_error: bool = False,
) -> SshKeyOutcome:
    def unknown(reason: str) -> SshKeyOutcome:
        return SshKeyOutcome("unknown", None, (None,) * len(CHECKS), reason)

    if runtime_error or before is None or after is None:
        return unknown("INCOMPLETE_NATIVE_STATE")
    if before.task != spec.task or after.task != spec.task:
        return unknown("NATIVE_TASK_SCOPE_MISMATCH")
    try:
        origin = urlsplit(site_origin)
        if (
            (origin.scheme, origin.hostname) != ("http", "127.0.0.1")
            or origin.port is None
            or origin.username is not None
            or origin.password is not None
            or origin.path not in ("", "/")
            or origin.query
            or origin.fragment
        ):
            return unknown("SITE_ORIGIN_UNAVAILABLE")
    except ValueError:
        return unknown("SITE_ORIGIN_UNAVAILABLE")
    if page is None:
        return unknown("TERMINAL_PAGE_UNAVAILABLE")
    if page.http_status is None or not 200 <= page.http_status < 500:
        return unknown("TERMINAL_TRANSPORT_UNAVAILABLE")
    if page.account_id is None and not page.login_page and not page.error_page:
        return unknown("CURRENT_ACCOUNT_UNAVAILABLE")
    expected = canonical_public_key(spec.parameters.public_key)
    account = before.account.id
    try:
        for row in before.keys.rows:
            value = row.get("key")
            if (
                row.get("user_id") == account
                and isinstance(value, str)
                and value.startswith("ssh-ed25519 ")
                and canonical_public_key(value) == expected
            ):
                return unknown("SUPPLIED_KEY_ALREADY_PRESENT")
        old = {row["id"] for row in before.keys.rows}
        inserted = [row for row in after.keys.rows if row["id"] not in old]
        target = inserted[0] if len(inserted) == 1 else None
        value = None if target is None else target.get("key")
        if target is not None and not isinstance(value, str):
            return unknown("MALFORMED_NATIVE_KEY")
        same_key = isinstance(value, str) and canonical_public_key(value) == expected
        sha = None if target is None else target.get("fingerprint_sha256")
        md5 = None if target is None else target.get("fingerprint")
        fingerprint_ok = fingerprints(spec.parameters.public_key, sha, md5)
    except (ValueError, TypeError):
        return unknown("MALFORMED_NATIVE_KEY")
    current = urlsplit(page.url)
    page_valid = (
        (current.scheme, current.netloc) == (origin.scheme, origin.netloc)
        and 200 <= page.http_status < 300
        and not page.login_page
        and not page.error_page
    )
    checks = (
        preserved(before, after),
        page_valid,
        len(inserted) == 1,
        same_key
        and target is not None
        and target.get("title") == spec.parameters.title,
        target is not None and target.get("user_id") == account,
        fingerprint_ok,
        page.account_id == account,
    )
    success = all(checks)
    return SshKeyOutcome(
        "success" if success else "failure",
        int(success),
        checks,
        "ALL_CHECKS_PASS" if success else "REQUIRED_CHECK_FAILED",
    )

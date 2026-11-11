"""Standalone trusted HTTP worker: one POST, no SDK, proxies or redirect retry.

Invoked with isolated Python. Credentials arrive only over stdin; stdout contains
bounded response bytes/status and sanitized error type names. Parent supervises
absolute deadline/cancellation including DNS/header/body stalls and reaps us.
No project imports: worker and parent are bound by the same release inventory.
"""

import base64
import http.client
import json
import resource
import ssl
import sys
from typing import Any
from urllib.parse import urlsplit


def exchange(spec: dict[str, Any]) -> dict[str, Any]:
    endpoint = urlsplit(spec["endpoint"])
    connection: http.client.HTTPConnection | None = None
    response: http.client.HTTPResponse | None = None
    result: dict[str, Any] = {
        "status": None,
        "body_base64": "",
        "complete": False,
        "errors": [],
    }
    body = b""
    errors: list[str] = []
    stage = "connect"
    try:
        if endpoint.scheme == "https":
            connection = http.client.HTTPSConnection(
                endpoint.hostname or "",
                endpoint.port,
                timeout=spec["timeout"],
                context=ssl.create_default_context(),
            )
        else:
            connection = http.client.HTTPConnection(
                endpoint.hostname or "", endpoint.port, timeout=spec["timeout"]
            )
        # HTTPConnection has no retry or redirect mechanism; exactly one request.
        stage = "request"
        connection.request(
            "POST",
            endpoint.path,
            body=base64.b64decode(spec["body_base64"], validate=True),
            headers={
                "Authorization": "Bearer " + spec["credential"],
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )
        stage = "headers"
        response = connection.getresponse()
        result["status"] = response.status
        try:
            stage = "body"
            body = response.read(spec["max_response_bytes"] + 1)
        except http.client.IncompleteRead as error:
            body = error.partial[: spec["max_response_bytes"]]
            raise
        if len(body) > spec["max_response_bytes"]:
            body = body[: spec["max_response_bytes"]]
            errors.append("ResponseLimit")
        elif response.length not in (None, 0):
            errors.append("IncompleteRead")
        else:
            result["complete"] = True
    except BaseException as error:
        errors.append(stage + "_" + type(error).__name__)
    finally:
        for name, item in (("response", response), ("connection", connection)):
            if item is not None:
                try:
                    item.close()
                except BaseException as error:
                    errors.append(name + "_close_" + type(error).__name__)
    # A provider must not cause the known credential to be persisted in evidence.
    if spec["credential"].encode() in body:
        body = b""
        errors.append("CredentialEchoSuppressed")
    result["body_base64"] = base64.b64encode(body).decode("ascii")
    result["errors"] = errors
    result["complete"] = result["complete"] and not errors
    return result


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        raw = sys.stdin.buffer.read(256 * 1024 * 1024 + 1)
        if len(raw) > 256 * 1024 * 1024:
            raise ValueError("Input bound")
        result = exchange(json.loads(raw))
    except BaseException as error:
        result = {
            "status": None,
            "body_base64": "",
            "complete": False,
            "errors": [type(error).__name__],
        }
    sys.stdout.buffer.write(json.dumps(result, separators=(",", ":")).encode())
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

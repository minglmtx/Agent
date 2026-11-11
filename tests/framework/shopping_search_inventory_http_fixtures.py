"""Local protocol faults for exact Shopping PHP; not a search implementation."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlsplit


class ContentsServer:
    def __init__(self, fault: str, hidden: bool) -> None:
        self.fault = fault
        self.names = ["catalog"]
        if hidden:
            self.names.insert(0, ".ds-events-2026.11.08-000001")
        self.calls: list[tuple[str, str]] = []
        self.stats_reads = self.alias_reads = 0
        self.deleted: list[str] = []
        self.current = ""
        self.source = b'{"value":1.2300,"nested":{"original":"bytes"}}'

    def metadata(self) -> dict[str, Any]:
        return dict(
            cluster_uuid="original-cluster",
            indices={
                n: dict(
                    state="open",
                    version=1,
                    settings=dict(index=dict(number_of_shards="1")),
                    mappings={},
                    aliases=["catalog-alias"] if n == "catalog" else [],
                )
                for n in self.names
            },
        )

    def aliases(self) -> dict[str, Any]:
        return {
            n: dict(aliases={"catalog-alias": {}} if n == "catalog" else {})
            for n in self.names
        }

    def reply(self, count: int) -> dict[str, Any]:
        hit = dict(_index=self.current, _id="one")
        return dict(
            _scroll_id=self.current + "-scroll",
            timed_out=False,
            _shards=dict(total=1, successful=1, failed=0),
            hits=dict(total=dict(value=1, relation="eq"), hits=[hit] if count else []),
        )

    def response(self, method: str, target: str) -> tuple[int, Any]:
        self.calls.append((method, target))
        url = urlsplit(target)
        path = unquote(url.path)
        query = parse_qs(url.query)
        if path == "/":
            return 200, dict(
                cluster_uuid="original-cluster", version=dict(number="7.17.0")
            )
        if path == "/_cluster/state/metadata":
            return 200, dict(metadata=self.metadata())
        if path == "/_stats":
            self.stats_reads += 1
            names = list(self.names)
            if (
                query.get("expand_wildcards") != ["all"]
                or self.fault == "missing-stat-index"
            ):
                names = ["catalog"]
            rows: dict[str, Any] = {
                n: dict(
                    shards={
                        "0": [
                            dict(
                                routing=dict(primary=True, state="STARTED"),
                                seq_no=dict(
                                    max_seq_no=0,
                                    local_checkpoint=0,
                                    global_checkpoint=0,
                                ),
                            )
                        ]
                    }
                )
                for n in names
            }
            if self.fault == "missing-primary":
                rows[names[0]]["shards"]["0"][0]["routing"]["primary"] = False
            if self.fault == "changed-watermark" and self.stats_reads > 1:
                rows[names[0]]["shards"]["0"][0]["seq_no"]["max_seq_no"] = 1
            return 200, dict(
                _shards=dict(total=len(names), successful=len(names), failed=0),
                indices=rows,
            )
        if path == "/_all":
            self.alias_reads += 1
            value = self.aliases()
            if (
                query.get("expand_wildcards") != ["all"]
                or self.fault == "missing-alias-index"
            ):
                value = {"catalog": value["catalog"]}
            if self.fault == "extra-alias-index":
                value["unexpected"] = dict(aliases={})
            if self.fault == "missing-alias-object":
                value[self.names[0]] = {}
            if self.fault == "array-alias-object":
                value[self.names[0]] = dict(aliases=[])
            if self.fault == "alias-name-mismatch":
                value["catalog"]["aliases"] = {"other-alias": {}}
            if self.fault == "changed-alias-definition" and self.alias_reads > 1:
                value["catalog"]["aliases"]["catalog-alias"] = {"is_write_index": True}
            return 200, value
        if path == "/_alias":
            raise AssertionError("Incomplete legacy alias endpoint must not be called")
        if path == "/_search/scroll":
            if method == "DELETE":
                self.deleted.append(self.current)
                return 200, dict(succeeded=self.fault != "cleanup-failed")
            if self.fault in ("after-scroll-http", "after-scroll-and-cleanup"):
                return 503, dict(error="injected original HTTP failure")
            return 200, self.reply(1 if self.fault == "duplicate-document" else 0)
        if path.endswith("/_search"):
            self.current = path[1:].removesuffix("/_search")
            return 200, self.reply(1)
        if "/_source/" in path:
            if self.fault == "source-http":
                return 503, dict(error="original source unavailable")
            return 200, self.source
        raise AssertionError((method, target))


@contextmanager
def contents_server(
    fault: str = "none", *, hidden: bool = True
) -> Iterator[tuple[ContentsServer, int]]:
    state = ContentsServer(fault, hidden)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def handle_request(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            status, value = state.response(self.command, self.path)
            raw = (
                value
                if isinstance(value, bytes)
                else json.dumps(value, separators=(",", ":")).encode()
            )
            if state.fault == "bad-json" and self.path == "/_all?expand_wildcards=all":
                raw = b"{bad"
            if state.fault == "after-scroll-and-cleanup" and self.command == "DELETE":
                status = 503
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(raw)

        do_GET = handle_request
        do_POST = handle_request
        do_DELETE = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

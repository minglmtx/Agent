"""Private native attachment provenance; observes existing browser events only.

No click, navigation, request, response-body read or actor guidance is added.
Actual public selection is supplied before actions/when observations are issued;
a later terminal selection can never backfill an earlier download event.
"""
from copy import deepcopy
from pathlib import Path
from weakref import WeakKeyDictionary
from .map_osm_artifact import request_bbox


class NativeExportTransport:
    def __init__(self, context, origin):
        self.context = context
        self.origin = origin
        self.snapshots = WeakKeyDictionary()
        self.pages = {}
        self.responses = []
        self.requests = {}
        self.response_requests = {}
        self.used_responses = set()
        self.events = []
        self.faults = []
        self.closed = False
        self.sequence = 0
        self.context.on("page", self.attach)
        self.context.on("request", self.request)
        self.context.on("response", self.response)
        for page in context.pages:
            self.attach(page)

    def attach(self, page):
        if page not in self.pages and not self.closed:
            callback = lambda item: self.download(page, item)
            self.pages[page] = callback
            page.on("download", callback)

    def observe(self, page, snapshot):
        if self.closed:
            raise RuntimeError("Native export transport observer is closed")
        if not isinstance(snapshot, dict):
            raise ValueError("Actual public snapshot required")
        self.snapshots[page] = deepcopy(snapshot)

    def request(self, request):
        try:
            request_bbox(request.url, self.origin)
        except ValueError:
            return
        self.sequence += 1
        try:
            page = request.frame.page
            self.requests[request] = {
                "sequence": self.sequence, "page": page,
                "snapshot": deepcopy(self.snapshots.get(page)),
            }
        except Exception:
            self.faults.append({"phase": "native_request_snapshot", "sequence": self.sequence})

    def response(self, response):
        try:
            request_bbox(response.url, self.origin)
        except ValueError:
            return
        self.sequence += 1
        try:
            headers = response.headers
            record = {"sequence": self.sequence, "url": response.url,
                      "http_status": response.status,
                      "content_type": headers.get("content-type", ""),
                      "content_disposition": headers.get("content-disposition", "")}
            self.responses.append(record)
            self.response_requests[record["sequence"]] = self.requests.get(response.request)
        except Exception:
            self.faults.append({"phase": "native_response_metadata", "sequence": self.sequence})

    def download(self, page, item):
        self.sequence += 1
        event = {"download_id": len(self.events) + 1, "sequence": self.sequence,
                 "filename": str(item.suggested_filename)[:256], "native": False}
        try:
            request_bbox(item.url, self.origin)
        except ValueError:
            self.events.append(event)
            return
        event.update(native=True, url=item.url)
        candidates = [r for r in self.responses if r["url"] == item.url
                      and r["sequence"] < event["sequence"]
                      and r["sequence"] not in self.used_responses
                      and (self.response_requests.get(r["sequence"]) or {}).get("page") is page]
        # A later observation cannot retroactively supply prerequisites for an
        # earlier request. Ambiguous responses are capture errors, not guesses.
        response = candidates[0] if len(candidates) == 1 else None
        event["response"] = deepcopy(response)
        request = self.response_requests.get(response["sequence"]) if response else None
        snapshot = request["snapshot"] if request else None
        event["request_sequence"] = request["sequence"] if request else None
        event["selection_observed_before_request"] = snapshot is not None
        if response:
            self.used_responses.add(response["sequence"])
        event["selection_snapshot"] = deepcopy(snapshot)
        event["selection_observed_before_download"] = snapshot is not None
        self.events.append(event)

    def audit(self, directory):
        """Use recorder-owned files/IDs, verifying size/hash before inspection."""
        from .gitlab_download_task import load_artifacts
        import json
        directory = Path(directory)
        artifacts = load_artifacts(directory)
        raw = json.loads((directory / "downloads.json").read_text()) if (directory / "downloads.json").exists() else {"downloads": []}
        rows = raw["downloads"]
        if self.faults:
            raise ValueError("Native attachment metadata capture failed")
        if len(rows) != len(self.events):
            raise ValueError("Native download events and shared recorder differ")
        for row, event in zip(rows, self.events):
            if row.get("download_id") != event["download_id"] or row.get("filename") != event["filename"]:
                raise ValueError("Download identity differs between observer and recorder")
            if row.get("status") == "failed":
                raise ValueError("Actual started native download transport failed")
        result = []
        for row, payload in artifacts:
            event = self.events[row["download_id"] - 1]
            if event["native"]:
                if event.get("response") is None:
                    raise ValueError("Native attachment lacks actual HTTP metadata")
                if event.get("selection_observed_before_download") is not True:
                    raise ValueError("Native attachment lacks prior public selection capture")
                if (event.get("selection_observed_before_request") is not True
                        or not event["request_sequence"] < event["response"]["sequence"] < event["sequence"]):
                    raise ValueError("Native attachment lacks request-bound selection capture")
            result.append({"record": row, "payload": payload, "event": deepcopy(event),
                           "file": str(directory / ("artifact-%04d.bin" % row["download_id"]))})
        return result

    def metadata(self):
        return {"events": deepcopy(self.events), "faults": list(self.faults),
                "selection_terminal_backfilled": False, "extra_requests": 0, "extra_actions": 0}

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.context.remove_listener("page", self.attach)
        self.context.remove_listener("request", self.request)
        self.context.remove_listener("response", self.response)
        for page, callback in self.pages.items():
            page.remove_listener("download", callback)
        self.pages.clear()
        self.requests.clear()
        self.response_requests.clear()

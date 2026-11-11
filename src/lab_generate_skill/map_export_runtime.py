"""Optional normal Export lifecycle; no per-task execution policy.

The original three information kinds use public schemas and actual terminal
map state. Independent settings/DB references and transport evidence are only
used by the evaluator after rollout, never as actor/teacher instructions.
"""
from copy import deepcopy
from pathlib import Path
from . import map_export_normal as normal
from . import map_osm_artifact as artifact
from .io_utils import atomic_write_json
from .map_export_transport import NativeExportTransport

EPISODE_REFERENT_VERSION = "map-export-first-actual-episode-default-v1"

def actual_default_export_bounds(snapshot):
    """Private referent from the first real inactive native Export form.

    A different worker/browser layout may expose a different default rectangle.
    Never adopt a selected/edited rectangle or relax form/geometry agreement.
    """
    from . import map_export_native_geometry as geometry
    from . import map_frontier_capabilities as cap
    try:
        form=snapshot["panel"]["export_form"]
        if not isinstance(form,dict) or form.get("selection_active") is not False:
            return None
        values=list(cap.form_bounds(snapshot["panel"]))
        if snapshot["view"].get("map_visible") is not True:
            return None
        if not geometry.bounds_match_projection(values,snapshot["view"],snapshot["size"]):
            return None
        return values
    except (KeyError,TypeError,ValueError):
        return None



def enabled(contract):
    # Ordered layer -> download tasks have a separate, composition-bound gate.
    # Never validate them as plain exports or authorize them from plain proofs.
    if 'ordered_export' in contract:
        return False
    if contract.get("map_export") is not None:
        normal.validate(contract)
        return True
    return False


def fields(contract):
    return deepcopy(normal.FIELDS.get(normal.validate(contract)["kind"]))


def require_admission(contract, proof):
    normal.require_admission(contract, proof)
    if contract.get("heldout_quarantine") or contract.get("eligible_for_training") is not False:
        raise ValueError("Original development/explicit derived task only")
    task_cycle_views(contract, proof, validated=True)
    return True


def task_cycle_views(contract, proof, *, validated=False):
    if not validated:
        normal.require_admission(contract, proof)
    views=[]
    for cycle in proof["cycles"]:
        rows=[r for r in cycle["tasks"] if r.get("task_id")==contract["task_id"]]
        if len(rows)!=1:
            raise ValueError("Exactly one source-bound normal task row required")
        row=rows[0]
        if (row.get("source_task_id")!=contract["source_task_id"]
            or row.get("original_goal")!=contract["original_goal"]
            or row.get("actual_test_goal")!=contract["goal"]
            or row.get("derived_task")!=contract["completion_revision"]["derived_task"]):
            raise ValueError("Task/source/goal/derived provenance differs")
        view=deepcopy(row)
        for key in ("cycle","initial_fingerprint","final_fingerprint","fresh_instance_id"):
            view[key]=cycle[key]
        views.append(view)
    if views[0]["reference"]!=views[1]["reference"]:
        raise ValueError("Native source setting/default referent differs across fresh cycles")
    return views


class MapExportHooks:
    def __init__(self, contract, proof, directory):
        require_admission(contract,proof)
        self.contract=contract
        self.directory=Path(directory)
        self.cycles=task_cycle_views(contract,proof)
        self.reference=deepcopy(self.cycles[0]["reference"])
        self.episode_default_export=None
        if contract["map_export"]["kind"]=="different_selection":
            # Independent CPU settings remain pinned, but its browser rectangle
            # cannot be the referent of this actual rollout.
            self.reference.pop("first_export_bounds",None)
        self.initial=None
        self.current=None
        self.transport=None
        self.timeline=[]

    def verify_baseline(self, site, initial_fingerprint):
        if initial_fingerprint!=self.cycles[0]["initial_fingerprint"]:
            raise RuntimeError("Native selected geographic baseline differs from both normal controls")
        from probe_map_export_normal import native_reference
        actual=native_reference(site,self.directory)
        if any(actual.get(key)!=self.reference.get(key) for key in
               ("maximum_area_square_degrees","unit","native_setting_verified")):
            raise RuntimeError("Independent native direct-export setting differs")
        atomic_write_json(self.directory/"native-export-setting-reference-before.json",actual)

    def attach(self, context, site_origin):
        if self.transport is not None:
            raise RuntimeError("One transport observer per task context required")
        self.transport=NativeExportTransport(context,site_origin)

    def observe_initial(self, page):
        from .map_export_initial import capture_initial
        self.initial=capture_initial(page,self.contract,
            site_origin=self.transport.origin if self.transport is not None else None)
        atomic_write_json(self.directory/"initial-native-export-snapshot.json",self.initial)
        self.record(page,event="initial")

    def record(self, page, *, event="observation"):
        snapshot=normal.read_snapshot(page)
        self.current=snapshot
        if self.contract["map_export"]["kind"]=="different_selection" and self.episode_default_export is None:
            bounds=actual_default_export_bounds(snapshot)
            if bounds is not None:
                self.reference["first_export_bounds"]=bounds
                self.episode_default_export={"version":EPISODE_REFERENT_VERSION,
                    "event":event,"timeline_index":len(self.timeline),
                    "actual_snapshot":deepcopy(snapshot),"first_export_bounds":bounds,
                    "private_reference_values_provided":False,"actor_strategy_modified":False}
                atomic_write_json(self.directory/"actual-episode-default-export-reference.json",self.episode_default_export)
        self.timeline.append({"event":event,"actual_snapshot":snapshot,"private_expected_values_added":False})
        if self.transport is not None:self.transport.observe(page,snapshot)
        atomic_write_json(self.directory/"native-export-observations.json",self.timeline)
        return snapshot

    def before_action(self,page):
        return self.record(page,event="before_action")

    def terminal(self,page,terminal):
        terminal["map_export"]=self.record(page,event="terminal")
        atomic_write_json(self.directory/"terminal-native-export.json",terminal["map_export"])
        atomic_write_json(self.directory/"terminal-page.json",terminal)

    def close(self):
        if self.transport is not None:
            self.transport.close()
            atomic_write_json(self.directory/"native-export-transport.json",self.transport.metadata())

    def evaluate(self, site, page, answer, *, runtime_error=None):
        def unknown(reason):return {"version":normal.VERSION,"status":"unknown","reward":None,"checks":{},"reason":reason}
        if runtime_error:return unknown("Environment or inference error")
        if self.initial is None:return unknown("Native initial observation unavailable")
        current=(page or {}).get("map_export")
        if self.contract["map_export"]["kind"]=="different_selection" and self.episode_default_export is None:
            if isinstance((current or {}).get("panel",{}).get("export_form"),dict):
                return unknown("Actual episode default Export rectangle was not captured before selection")
            # No Export form/selection was reached; its bounds cannot matter to
            # failure. Keep the independent value only for this no-op negative.
            unused=deepcopy(self.reference)
            unused["first_export_bounds"]=self.cycles[0]["reference"]["first_export_bounds"]
            return normal.evaluate(self.contract,page,answer,self.initial,current,unused,site_origin=site.url)
        if self.contract["map_export"]["kind"]!="osm_download":
            return normal.evaluate(self.contract,page,answer,self.initial,current,self.reference,site_origin=site.url)
        if self.transport is None:return unknown("Native download observer was not installed")
        try:items=self.transport.audit(self.directory/"browser-downloads")
        except (ValueError,OSError,KeyError,TypeError):return unknown("Native downloaded artifact or transport capture unavailable")
        judgments=[]
        for item in items:
            event=item["event"]
            if not event["native"]:continue
            meta=dict(event["response"],**item["record"])
            if type(meta.get("http_status"))is not int:
                return unknown("Native attachment HTTP status capture unavailable")
            if meta["http_status"]>=500:
                return unknown("Native attachment service returned a server error")
            # Completed wrong formats/objects are model/task failures, not
            # capture failures. Missing/corrupt recorder-owned files were
            # separately rejected above before this native inspection.
            try:parsed=artifact.parse_xml(item["payload"])
            except ValueError:continue
            if not parsed["in_bbox_nodes"]:continue
            selection=event["selection_snapshot"]
            if not isinstance(selection.get("panel",{}).get("export_form"),dict):continue
            try:
                bounds=artifact.request_bbox(event["url"],site.url)
                from .map_osm_native_reference import capture_complete_reference
                from probe_map_osm_export_capability_v3 import fetch
                ident=str(item["record"]["download_id"])
                _,_,ref,_=capture_complete_reference(site,bounds,self.directory,"terminal-download-"+ident,fetcher=fetch)
            except (ValueError,RuntimeError,OSError):return unknown("Independent native full geometry reference unavailable")
            download={"metadata":meta,"file":item["file"],"private_native_reference":ref}
            result=normal.evaluate(self.contract,page,answer,self.initial,current,self.reference,
                        site_origin=site.url,download=download,selection=selection)
            judgments.append(result)
            if result["status"]=="success":return result
        if any(j["status"]=="unknown"for j in judgments):return next(j for j in judgments if j["status"]=="unknown")
        # Explicitly no valid received artifact: opening a form or receiving a
        # wrong attachment cannot become success and is ordinary failure.
        return normal.evaluate(self.contract,page,answer,self.initial,current,self.reference,site_origin=site.url)

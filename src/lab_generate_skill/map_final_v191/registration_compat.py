"""Check current additive branches, then compare historical dependency bytes.

Only the four declared files are projected. Current executable bytes and the
actual five-source entry review are checked before historical-schema checks.
No historical code is imported or used for execution.
"""
from pathlib import Path
import hashlib
import json

SOURCE = "01ccdfd9a75d86f713e4"
PREFIX = "src/lab_generate_skill/"
NAMES = frozenset(PREFIX + name + ".py" for name in (
    "site_worker", "website_batch_profile", "native_goal_dispatch", "reviewed_map_registry"))
METADATA = {
    "scripts/map_route_location/offline-review.json": "direct_runtime_files",
    "scripts/map_surfaces/offline-review.json": "reused_runtime_files",
}


def require_update(update, *, source, project, read):
    if (source != SOURCE or update.get("source_task_id") != SOURCE
            or update.get("version") != "registration-final-map-compatibility-v191"
            or set(update.get("changes", {})) != NAMES | METADATA.keys()):
        raise ValueError("Exact registration source, four code files and two inventories required")
    projection = read(update["projection"])
    native = read(update["native_delta"])
    review = read(update["entry_review"])
    capsule = read(review["capsule"])
    previous = read(projection["formal_capsule"])
    if (not projection.get("passed") or not native.get("passed")
            or native.get("base_capsule") != projection.get("formal_capsule")
            or not native.get("exact_default_source_projection")
            or not review.get("passed") or review.get("source_count") != 5
            or review.get("actual_requests_reconstructed") != 21
            or set(projection.get("changes", {})) != NAMES
            or set(native.get("changes", {})) != NAMES - {PREFIX+"reviewed_map_registry.py"}):
        raise ValueError("Qualified exact additive source projection required")
    old_bytes = {}
    project = Path(project).resolve()
    for name, change in update["changes"].items():
        if name in METADATA:
            if change["previous_sha256"] != previous["members"][name]["sha256"]:
                raise ValueError("Previous dependency inventory identity differs")
            before = read(change["previous_file"], json_value=False)
            if hashlib.sha256(before).hexdigest() != change["previous_sha256"]:
                raise ValueError("Historical dependency inventory differs")
            current = read(dict(path=str(project/name), sha256=change["current_sha256"]), json_value=False)
            expected = json.loads(before)
            refreshed = []
            for row in expected[METADATA[name]]:
                relative = PREFIX + Path(row["path"]).name
                if relative in NAMES:
                    pair = projection["changes"][relative]
                    if row["sha256"] != pair["old_sha256"]:
                        raise ValueError("Inventory does not name exact previous dependency")
                    row["sha256"] = pair["current_sha256"]
                    refreshed.append(relative)
            if (not refreshed or sorted(refreshed) != change["refreshed_dependencies"]
                    or expected != json.loads(current)):
                raise ValueError("Inventory changed beyond qualified dependency hashes")
            old_bytes[name] = before
            continue
        pair = projection["changes"][name]
        extension = None
        current_digest = pair["current_sha256"]
        if name == PREFIX+"reviewed_map_registry.py" and update.get("eiffel_extension") is not None:
            extension = read(update["eiffel_extension"])
            if extension["previous_sha256"] != current_digest:
                raise ValueError("Eiffel extension does not follow the qualified five-source registry")
            current_digest = extension["current_sha256"]
        if (change["previous_sha256"] != previous["members"][name]["sha256"]
                or change["previous_sha256"] != pair["old_sha256"]
                or change["current_sha256"] != current_digest
                or pair["current_sha256"] != capsule["members"][name]["sha256"]):
            raise ValueError("Current/previous dependency and executed entry identities differ")
        before = read(change["previous_file"], json_value=False)
        if hashlib.sha256(before).hexdigest() != change["previous_sha256"]:
            raise ValueError("Historical dependency differs")
        raw = read(dict(path=str(project/name), sha256=change["current_sha256"]), json_value=False)
        if extension is not None:
            from ..map_eiffel_v191.extension import project_registry
            raw = project_registry(raw, extension, read)
        projected = raw.decode()
        if name in native["changes"]:
            edits = native["changes"][name]["edits"]
        else:
            edits = [
                dict(current=projection["registry_additions"], previous=""),
                dict(current=projection["profile_current"], previous=projection["profile_previous"]),
            ]
        for edit in reversed(edits):
            if projected.count(edit["current"]) != 1:
                raise ValueError("Exact additive branch is missing or duplicated")
            projected = projected.replace(edit["current"], edit["previous"])
        if projected.encode() != before:
            raise ValueError("Existing dependency behavior changed outside qualified branches")
        old_bytes[name] = before

    def legacy_dependency_read(ref, *, json_value=True):
        path = Path(ref["path"])
        try:
            name = path.relative_to(project).as_posix()
        except ValueError:
            return read(ref, json_value=json_value)
        change = update["changes"].get(name)
        if change is None or ref["sha256"] != change["previous_sha256"]:
            return read(ref, json_value=json_value)
        # Recheck current bytes on every legacy comparison; read() tracks them.
        read(dict(path=str(path), sha256=change["current_sha256"]), json_value=False)
        value = old_bytes[name]
        return json.loads(value) if json_value else value
    return legacy_dependency_read

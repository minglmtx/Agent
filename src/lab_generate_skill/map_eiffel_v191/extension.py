"""Exact additional registry branch; no change to any previous Map branch."""
import hashlib

SOURCE="b4eecdad9946f2165795"
RELATIVE="src/lab_generate_skill/reviewed_map_registry.py"
ADDITION="    'eiffel_search_v191': ('map_eiffel_v191.catalog', 'EiffelCatalog', 'map_eiffel_v191.bridge', 'EiffelAdapter'),\n"
BEFORE_PROFILE="if kind in ('remaining_routes','remaining_four_v191') and catalog.config.get('asset_manifest') is not None:"
AFTER_PROFILE="if kind in ('remaining_routes','remaining_four_v191','eiffel_search_v191') and catalog.config.get('asset_manifest') is not None:"


def project_registry(raw,extension,read):
    if (extension.get("version")!="single-eiffel-registry-extension-v191"
            or extension.get("source_task_id")!=SOURCE or extension.get("relative")!=RELATIVE):
        raise ValueError("Exactly one declared Eiffel registry extension required")
    entry=read(extension["entry_review"])
    actor=read(extension["actor_review"])
    if (not entry.get("passed")or entry.get("source_task_id")!=SOURCE
            or entry.get("actual_control_native_results_replayed")!=6
            or not actor.get("passed")or actor.get("source_task_id")!=SOURCE
            or not actor.get("source_result_accepted")or actor.get("actual_actor_attempts")!=1):
        raise ValueError("Qualified native input and actual first search Actor required")
    before=read(extension["previous_file"],json_value=False)
    if (hashlib.sha256(before).hexdigest()!=extension["previous_sha256"]
            or hashlib.sha256(raw).hexdigest()!=extension["current_sha256"]):
        raise ValueError("Current/previous registry bytes differ")
    text=raw.decode()
    if text.count(ADDITION)!=1 or text.count(AFTER_PROFILE)!=1:
        raise ValueError("Exact single-source registry and profile additions required")
    projected=text.replace(ADDITION,"").replace(AFTER_PROFILE,BEFORE_PROFILE).encode()
    if projected!=before:
        raise ValueError("An existing Map registry branch changed")
    return projected

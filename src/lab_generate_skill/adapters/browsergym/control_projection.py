from typing import Any

"""Expose native visible control styling from the captured public DOM.

No actions, page mutation, task-specific IDs, private references or inferred
recovery advice. CSS 'disabled' is reported as CSS state rather than asserted
to be the HTML disabled property. Native device-location group active/requesting
CSS states are literal flags, never a statement that a task has succeeded.
Existing AX visibility filtering still applies.
"""
PUBLIC_STATE_GROUPS = {"control-locate": ("active", "requesting")}


def _visible_layout_indices(doc: Any) -> Any:
    layout = doc.get("layout", {})
    output = set()
    for offset, index in enumerate(layout.get("nodeIndex", [])):
        bounds = layout.get("bounds", [])
        if (
            offset >= len(bounds)
            or len(bounds[offset]) != 4
            or bounds[offset][2] <= 0
            or (bounds[offset][3] <= 0)
        ):
            continue
        output.add(index)
    return output


def with_public_control_state(tree: Any, dom: Any, extra_properties: Any = None) -> Any:
    state: Any
    if not isinstance(dom, dict):
        return tree
    strings = dom.get("strings", [])
    states = {}
    ambiguous = set()
    roles = {
        "link",
        "button",
        "checkbox",
        "radio",
        "combobox",
        "textbox",
        "menuitem",
        "switch",
    }
    exposed = {
        n.get("backendDOMNodeId")
        for n in tree.get("nodes", [])
        if not n.get("ignored") and n.get("role", {}).get("value") in roles
    }
    visible_controls = {
        n.get("backendDOMNodeId")
        for n in tree.get("nodes", [])
        if (extra_properties or {}).get(n.get("browsergym_id"), {}).get("visibility", 0)
        >= 0.5
    }
    for doc in dom.get("documents", []):
        nodes = doc.get("nodes", {})
        ids = nodes.get("backendNodeId", [])
        attrs = nodes.get("attributes", [])
        parents = nodes.get("parentIndex", [])
        if len(attrs) != len(ids) or len(parents) != len(ids):
            continue

        def attributes(index: Any) -> Any:
            raw = attrs[index]
            if len(raw) % 2:
                return {}
            return {strings[raw[i]]: strings[raw[i + 1]] for i in range(0, len(raw), 2)}

        visible = _visible_layout_indices(doc)
        for index, backend in enumerate(ids):
            if backend not in exposed:
                continue
            native = attributes(index)
            state = {}
            at = index
            for _ in range(4):
                if at < 0 or at >= len(ids):
                    break
                classes = attributes(at).get("class", "").split()
                groups = [g for g in PUBLIC_STATE_GROUPS if g in classes]
                if groups:
                    descendants = []
                    for child, child_backend in enumerate(ids):
                        if child_backend not in exposed:
                            continue
                        ancestor = child
                        for _ in range(4):
                            if ancestor < 0 or ancestor >= len(ids):
                                break
                            if ancestor == at:
                                descendants.append(child)
                                break
                            ancestor = parents[ancestor]
                    if (
                        len(groups) == 1
                        and descendants == [index]
                        and (index in visible)
                        and (at in visible)
                        and (backend in visible_controls)
                    ):
                        for flag in PUBLIC_STATE_GROUPS[groups[0]]:
                            state["css_" + flag] = flag in classes
                    break
                at = parents[at]
            if "disabled" not in native.get("class", "").split():
                if state:
                    if backend in states:
                        ambiguous.add(backend)
                    states[backend] = state
                continue
            state["css_disabled"] = True
            hints = []
            at = index
            for _ in range(3):
                if at < 0 or at >= len(ids):
                    break
                a = attributes(at)
                if at != index and "disabled" not in a.get("class", "").split():
                    break
                values = [
                    a.get(k, "").strip()
                    for k in ("title", "data-original-title", "data-bs-original-title")
                ]
                values = list(dict.fromkeys((v for v in values if v)))
                if len(values) == 1:
                    hints = values
                    break
                if len(values) > 1:
                    break
                at = parents[at]
            if hints:
                state["control_hint"] = hints[0]
            if backend in states:
                ambiguous.add(backend)
            states[backend] = state
    output = []
    for node in tree.get("nodes", []):
        backend = node.get("backendDOMNodeId")
        state = states.get(backend)
        if state and backend not in ambiguous:
            props = [
                x for x in node.get("properties", []) if x.get("name") not in state
            ]
            props += [
                {
                    "name": k,
                    "value": {
                        "type": "boolean" if isinstance(v, bool) else "string",
                        "value": v,
                    },
                }
                for (k, v) in state.items()
            ]
            node = {**node, "properties": props}
        output.append(node)
    return {**tree, "nodes": output}

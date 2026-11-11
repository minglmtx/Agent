"""Pure public AX projection, preserved from the workspace implementation."""

from typing import Any


def with_rendered_inline_text(tree: Any, dom: Any, extra_properties: Any) -> Any:
    child: Any
    "Preserve rendered spacing across inline nodes from the same DOM snapshot.\n\n    AX separates inline emoji/emphasis from adjacent text and loses the spacing\n    at those boundaries. Supplement small plain paragraphs with the browser's\n    rendered text fragments, never textContent from hidden nodes or a database.\n    Keep the original AX nodes and action IDs; ordinary visibility filtering and\n    the model input budget still apply.\n    "
    if not isinstance(dom, dict):
        return tree
    from collections import defaultdict

    strings = dom.get("strings", [])
    candidates = {}
    ambiguous = set()
    exposed_text = {
        n.get("backendDOMNodeId")
        for n in tree.get("nodes", [])
        if not n.get("ignored") and n.get("role", {}).get("value") == "StaticText"
    }
    safe_inline = {"SPAN", "A", "B", "STRONG", "EM", "I", "SMALL", "CODE", "GL-EMOJI"}
    for doc in dom.get("documents", []):
        nodes = doc.get("nodes", {})
        layout = doc.get("layout", {})
        required = ("nodeName", "parentIndex", "nodeType", "nodeValue", "backendNodeId")
        if any((k not in nodes for k in required)):
            continue
        children = defaultdict(list)
        for index, parent in enumerate(nodes["parentIndex"]):
            children[parent].append(index)
        rendered = {
            index: strings[text] if text >= 0 else ""
            for (index, text) in zip(
                layout.get("nodeIndex", []), layout.get("text", [])
            )
        }
        for index, name in enumerate(nodes["nodeName"]):
            if strings[name] != "P" or index not in rendered:
                continue
            stack = list(reversed(children[index]))
            fragments = []
            allowed = True
            while stack:
                child = stack.pop()
                kind = nodes["nodeType"][child]
                if kind == 3:
                    value = rendered.get(child)
                    native_index = nodes["nodeValue"][child]
                    native = strings[native_index] if native_index >= 0 else ""
                    if native.strip() and (
                        value is None
                        or nodes["backendNodeId"][child] not in exposed_text
                    ):
                        allowed = False
                        break
                    if value:
                        fragments.append(value)
                elif kind == 1 and strings[nodes["nodeName"][child]] in safe_inline:
                    stack.extend(reversed(children[child]))
                else:
                    allowed = False
                    break
            if not allowed or len(fragments) < 2:
                continue
            value = "".join(fragments)
            if not value.strip() or len(value) > 512:
                continue
            backend = nodes["backendNodeId"][index]
            if backend in candidates:
                ambiguous.add(backend)
            candidates[backend] = value
    axnodes = {n["nodeId"]: n for n in tree.get("nodes", [])}
    output = []
    for node in tree.get("nodes", []):
        backend = node.get("backendDOMNodeId")
        value = candidates.get(backend)
        fully_visible = (
            extra_properties.get(node.get("browsergym_id"), {}).get("visibility", 0)
            >= 1
        )
        if (
            value
            and fully_visible
            and (backend not in ambiguous)
            and (node.get("role", {}).get("value") == "paragraph")
        ):
            pending = list(node.get("childIds", []))
            hidden = False
            while pending:
                child = axnodes.get(pending.pop(), {})
                bid = child.get("browsergym_id")
                if bid and extra_properties.get(bid, {}).get("visibility", 0) < 0.5:
                    hidden = True
                    break
                pending.extend(child.get("childIds", []))
            if not hidden:
                props = [
                    p
                    for p in node.get("properties", [])
                    if p.get("name") != "rendered_text"
                ]
                node = {
                    **node,
                    "properties": props
                    + [
                        {
                            "name": "rendered_text",
                            "value": {"type": "string", "value": value},
                        }
                    ],
                }
        output.append(node)
    return {**tree, "nodes": output}


def with_rendered_generic_text(tree: Any, dom: Any, extra: Any) -> Any:
    """Keep a visible generic region's single directly rendered text label.

    Some editors implement a drop region as a plain div with an instructional
    text child, without HTML/ARIA drag attributes. Preserve that literal text
    and the region's existing bid; do not infer or assert drop semantics.
    Nested containers, hidden text and multi-part page summaries are excluded.
    """
    if not isinstance(dom, dict):
        return tree
    strings = dom.get("strings", [])
    rendered = {}
    ambiguous = set()
    for doc in dom.get("documents", []):
        nodes = doc.get("nodes", {})
        layout = doc.get("layout", {})
        backends = nodes.get("backendNodeId", [])
        types = nodes.get("nodeType", [])
        for idx, text_id in zip(layout.get("nodeIndex", []), layout.get("text", [])):
            if not (
                0 <= idx < len(backends)
                and idx < len(types)
                and (types[idx] == 3)
                and (0 <= text_id < len(strings))
            ):
                continue
            backend = backends[idx]
            if backend in rendered:
                ambiguous.add(backend)
            rendered[backend] = strings[text_id]
    by_id = {n["nodeId"]: n for n in tree.get("nodes", [])}
    output = []
    for node in tree.get("nodes", []):
        children = node.get("childIds", [])
        child = by_id.get(children[0], {}) if len(children) == 1 else {}
        backend = child.get("backendDOMNodeId")
        text = rendered.get(backend, "")
        if (
            node.get("role", {}).get("value") == "generic"
            and (not node.get("ignored"))
            and node.get("browsergym_id")
            and (extra.get(node["browsergym_id"], {}).get("visibility", 0) >= 0.5)
            and (child.get("role", {}).get("value") == "StaticText")
            and (not child.get("ignored"))
            and (backend not in ambiguous)
            and text.strip()
            and (len(text) <= 256)
            and (text.strip() == str(child.get("name", {}).get("value", "")).strip())
        ):
            props = [
                p
                for p in node.get("properties", [])
                if p.get("name") != "rendered_text"
            ]
            node = {
                **node,
                "properties": props
                + [
                    {
                        "name": "rendered_text",
                        "value": {"type": "string", "value": text},
                    }
                ],
            }
        output.append(node)
    return {**tree, "nodes": output}

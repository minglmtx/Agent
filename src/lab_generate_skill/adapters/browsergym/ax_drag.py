"""Pure public AX projection, preserved from the workspace implementation."""

from typing import Any
from .ax_native import with_native_clickable_regions
from .ax_inline import with_rendered_generic_text
from .ax_options import with_native_option_text


def with_native_drag_regions(tree: Any, dom: Any, extra: Any) -> Any:
    flags: Any
    if not isinstance(dom, dict):
        return tree
    strings = dom.get("strings", [])
    exposed = {
        n.get("backendDOMNodeId"): n
        for n in tree.get("nodes", [])
        if not n.get("ignored") and n.get("browsergym_id")
    }
    states = {}
    ambiguous = set()
    for doc in dom.get("documents", []):
        nodes = doc.get("nodes", {})
        backends, attributes = (
            nodes.get("backendNodeId", []),
            nodes.get("attributes", []),
        )
        if len(backends) != len(attributes):
            continue
        layout = doc.get("layout", {})
        rendered = {
            idx
            for (idx, bounds) in zip(
                layout.get("nodeIndex", []), layout.get("bounds", [])
            )
            if len(bounds) == 4 and bounds[2] > 0 and (bounds[3] > 0)
        }
        for idx, backend in enumerate(backends):
            node = exposed.get(backend)
            if node is None or idx not in rendered:
                continue
            bid = node["browsergym_id"]
            if extra.get(bid, {}).get("visibility", 0) < 0.5:
                continue
            native = attributes[idx]
            if len(native) % 2 or any(
                (type(i) is not int or i < 0 or i >= len(strings) for i in native)
            ):
                continue
            attrs = {
                strings[native[i]]: strings[native[i + 1]]
                for i in range(0, len(native), 2)
            }
            classes = attrs.get("class", "").split()
            flags = {}
            if attrs.get("draggable", "").lower() == "true":
                flags["html_draggable"] = True
            for native_class, flag in [
                ("ui-draggable", "css_draggable"),
                ("ui-droppable", "css_droppable"),
            ]:
                if native_class in classes:
                    flags[flag] = True
                    if native_class + "-disabled" in classes:
                        flags[flag + "_disabled"] = True
            dropeffect = attrs.get("aria-dropeffect", "").strip()
            if dropeffect and set(dropeffect.split()) <= {
                "copy",
                "execute",
                "link",
                "move",
                "none",
                "popup",
            }:
                flags["aria_dropeffect"] = dropeffect
            if not flags:
                continue
            if backend in states:
                ambiguous.add(backend)
            states[backend] = flags
    output = []
    for node in tree.get("nodes", []):
        backend = node.get("backendDOMNodeId")
        flags = states.get(backend)
        if flags and backend not in ambiguous:
            props = [
                x for x in node.get("properties", []) if x.get("name") not in flags
            ]
            props.extend(
                (
                    {
                        "name": k,
                        "value": {
                            "type": "boolean" if isinstance(v, bool) else "string",
                            "value": v,
                        },
                    }
                    for (k, v) in flags.items()
                )
            )
            node = {**node, "properties": props}
        output.append(node)
    return with_native_option_text(
        with_native_clickable_regions(
            with_rendered_generic_text({**tree, "nodes": output}, dom, extra), extra
        ),
        dom,
        extra,
    )

"""Pure public AX projection, preserved from the workspace implementation."""

from typing import Any


def with_native_option_text(tree: Any, dom: Any, extra: Any) -> Any:
    if not isinstance(dom, dict):
        return tree
    strings = dom.get("strings", [])
    candidates, ambiguous = ({}, set())
    ax = {}
    for node in tree.get("nodes", []):
        backend = node.get("backendDOMNodeId")
        if backend in ax:
            ambiguous.add(backend)
        ax[backend] = node
    for doc in dom.get("documents", []):
        nodes, layout = (doc.get("nodes", {}), doc.get("layout", {}))
        ids = nodes.get("backendNodeId", [])
        names, attrs, parents = (
            nodes.get(k, []) for k in ("nodeName", "attributes", "parentIndex")
        )
        types, values = (nodes.get("nodeType", []), nodes.get("nodeValue", []))
        if any(
            (len(seq) != len(ids) for seq in (names, attrs, parents, types, values))
        ):
            continue

        def string(index: Any) -> Any:
            if index == -1:
                return ""
            return (
                strings[index]
                if type(index) is int and 0 <= index < len(strings)
                else None
            )

        def attributes(index: Any) -> Any:
            row = attrs[index]
            if len(row) % 2 or any((string(i) is None for i in row)):
                return None
            if any((not string(row[i]) for i in range(0, len(row), 2))):
                return None
            return {string(row[i]): string(row[i + 1]) for i in range(0, len(row), 2)}

        bounds: dict[int, Any] = {}
        for index, box in zip(layout.get("nodeIndex", []), layout.get("bounds", [])):
            if index in bounds:
                bounds[index] = None
            else:
                bounds[index] = box
        children: dict[int, list[int]] = {}
        for i, parent in enumerate(parents):
            children.setdefault(parent, []).append(i)
        for index, backend in enumerate(ids):
            node = ax.get(backend, {})
            bid = node.get("browsergym_id")
            if (
                node.get("ignored")
                or node.get("role", {}).get("value") != "option"
                or str(node.get("name", {}).get("value", "")).strip()
                or (not bid)
                or (extra.get(bid, {}).get("visibility", 0) < 1)
                or (string(names[index]) != "OPTION")
            ):
                continue
            parent = parents[index]
            if (
                type(parent) is not int
                or not 0 <= parent < len(ids)
                or string(names[parent]) != "SELECT"
            ):
                continue
            option_attrs, select_attrs = (attributes(index), attributes(parent))
            if (
                option_attrs is None
                or select_attrs is None
                or option_attrs.get("label", "").strip()
            ):
                continue
            try:
                listbox = (
                    "multiple" in select_attrs or int(select_attrs.get("size", "1")) > 1
                )
            except ValueError:
                continue
            if not listbox:
                continue
            option_box, select_box = (bounds.get(index), bounds.get(parent))
            if (
                not option_box
                or not select_box
                or len(option_box) != 4
                or (len(select_box) != 4)
                or (option_box[2] <= 0)
                or (option_box[3] <= 0)
                or (select_box[2] <= 0)
                or (select_box[3] <= 0)
            ):
                continue
            x, y, width, height = option_box
            sx, sy, sw, sh = select_box
            if not (
                sx <= x
                and sy <= y
                and (x + width <= sx + sw)
                and (y + height <= sy + sh)
            ):
                continue
            child_ids = children.get(index, [])
            if not child_ids or any(
                (types[i] != 3 or string(values[i]) is None for i in child_ids)
            ):
                continue
            text = " ".join("".join((strings[values[i]] for i in child_ids)).split())
            contents = {
                source.get("value", {}).get("value")
                for source in node.get("name", {}).get("sources", [])
                if source.get("type") == "contents"
                and isinstance(source.get("value", {}).get("value"), str)
            }
            contents = {" ".join(value.split()) for value in contents if value.strip()}
            if not text or len(text) > 512 or contents != {text}:
                continue
            if backend in candidates:
                ambiguous.add(backend)
            candidates[backend] = text
    output = []
    for node in tree.get("nodes", []):
        backend = node.get("backendDOMNodeId")
        if backend in candidates and backend not in ambiguous:
            props = [
                p
                for p in node.get("properties", [])
                if p.get("name") != "rendered_option_text"
            ]
            node = {
                **node,
                "properties": props
                + [
                    {
                        "name": "rendered_option_text",
                        "value": {"type": "string", "value": candidates[backend]},
                    }
                ],
            }
        output.append(node)
    return {**tree, "nodes": output}

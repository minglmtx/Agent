"""Pure public AX projection, preserved from the workspace implementation."""

from typing import Any


def native_context(node: Any) -> Any:
    value = node.get("description", {}).get("value")
    if isinstance(value, str) and value.strip():
        return ("description", value)
    titles = []
    for source in node.get("name", {}).get("sources", []):
        if source.get("type") != "attribute" or source.get("attribute") != "title":
            continue
        value = source.get("attributeValue", source.get("value", {})).get("value")
        if isinstance(value, str) and value.strip() and (value not in titles):
            titles.append(value)
    if len(titles) == 1:
        return ("title", titles[0])
    return (None, None)


def with_native_descriptions(tree: Any) -> Any:
    nodes = []
    for node in tree.get("nodes", []):
        key, value = native_context(node)
        name = node.get("name", {}).get("value")
        if (
            isinstance(value, str)
            and value.strip()
            and (value.strip() != str(name or "").strip())
        ):
            props = [p for p in node.get("properties", []) if p.get("name") != key]
            node = {
                **node,
                "properties": props
                + [{"name": key, "value": {"type": "string", "value": value}}],
            }
        nodes.append(node)
    return {**tree, "nodes": nodes}


def with_keyboard_focusable_regions(tree: Any) -> Any:
    """Keep native focusable generic regions addressable in the text observation.

    BrowserGym ignores Chromium's ``focusable`` property and skips generic
    nodes with no remaining attributes. Preserve only a literal native True
    on a non-ignored generic node with its existing action ID. The additional
    property is a rendering alias, not a new role, label, ID or page action.
    Ordinary viewport filtering and input budgets still apply to this node.
    """
    output = []
    for node in tree.get("nodes", []):
        props = node.get("properties", [])
        focusable = [
            p.get("value", {}).get("value")
            for p in props
            if p.get("name") == "focusable"
        ]
        bid = node.get("browsergym_id")
        if (
            node.get("role", {}).get("value") == "generic"
            and (not node.get("ignored"))
            and isinstance(bid, str)
            and bid.strip()
            and (focusable == [True])
            and (type(focusable[0]) is bool)
            and (not any((p.get("name") == "keyboard_focusable" for p in props)))
        ):
            node = {
                **node,
                "properties": props
                + [
                    {
                        "name": "keyboard_focusable",
                        "value": {"type": "boolean", "value": True},
                    }
                ],
            }
        output.append(node)
    return {**tree, "nodes": output}


def with_native_clickable_regions(tree: Any, extra: Any) -> Any:
    """Preserve an existing visible generic control's native clickability.

    BrowserGym drops generic nodes before it renders its clickable metadata,
    even if Chromium supplies an accessible name. Keep the measured flag as
    an AX property; never infer clickability from names, CSS or task intent.
    """
    output = []
    for node in tree.get("nodes", []):
        bid = node.get("browsergym_id")
        state = extra.get(bid, {})
        bounds = state.get("bbox", [])
        if (
            node.get("role", {}).get("value") == "generic"
            and (not node.get("ignored"))
            and isinstance(bid, str)
            and bid
            and (state.get("clickable") is True)
            and (state.get("visibility", 0) >= 0.5)
            and (len(bounds) == 4)
            and (bounds[2] > 0)
            and (bounds[3] > 0)
        ):
            props = [
                x
                for x in node.get("properties", [])
                if x.get("name") != "native_clickable"
            ]
            node = {
                **node,
                "properties": props
                + [
                    {
                        "name": "native_clickable",
                        "value": {"type": "boolean", "value": True},
                    }
                ],
            }
        output.append(node)
    return {**tree, "nodes": output}

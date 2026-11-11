"""Exact original renderer membership index and private tile URL, no I/O."""

import hashlib
import ipaddress
from urllib.parse import urlsplit

PINNED_SHA256 = "19c69de257efcd54351f6344b8c3290fe9bbd2281312434a08f9a2d23d02f530"

BUILD_BEFORE = "    for (var node_id in nodes) {\n      var node = nodes[node_id];\n      if (this.interestingNode(node, ways, relations)) {\n        features.push(node);\n      }\n    }"

BUILD_AFTER = "    var membership = {wayNodes: new Set(), relationNodes: new Set()};\n    for (var wi = 0; wi < ways.length; wi++) {\n      for (var wn = 0; wn < ways[wi].nodes.length; wn++) {\n        membership.wayNodes.add(ways[wi].nodes[wn]);\n      }\n    }\n    for (var ri = 0; ri < relations.length; ri++) {\n      for (var rn = 0; rn < relations[ri].members.length; rn++) {\n        membership.relationNodes.add(relations[ri].members[rn]);\n      }\n    }\n\n    for (var node_id in nodes) {\n      var node = nodes[node_id];\n      if (this.interestingNode(node, ways, relations, membership)) {\n        features.push(node);\n      }\n    }"

INTERESTING_BEFORE = "  interestingNode: function (node, ways, relations) {\n    var used = false;\n\n    for (var i = 0; i < ways.length; i++) {\n      if (ways[i].nodes.indexOf(node) >= 0) {\n        used = true;\n        break;\n      }\n    }\n\n    if (!used) {\n      return true;\n    }\n\n    for (var i = 0; i < relations.length; i++) {\n      if (relations[i].members.indexOf(node) >= 0)\n        return true;\n    }"

INTERESTING_AFTER = "  interestingNode: function (node, ways, relations, membership) {\n    var used = false;\n\n    if (membership) {\n      used = membership.wayNodes.has(node);\n    } else {\n      for (var i = 0; i < ways.length; i++) {\n        if (ways[i].nodes.indexOf(node) >= 0) {\n          used = true;\n          break;\n        }\n      }\n    }\n\n    if (!used) {\n      return true;\n    }\n\n    if (membership) {\n      if (membership.relationNodes.has(node)) return true;\n    } else {\n      for (var i = 0; i < relations.length; i++) {\n        if (relations[i].members.indexOf(node) >= 0)\n          return true;\n      }\n    }"


def renderer_source(original: bytes, tile_url: str) -> str:
    if (
        type(original) is not bytes
        or hashlib.sha256(original).hexdigest() != PINNED_SHA256
    ):
        raise ValueError("Exact original native renderer bytes required")
    if type(tile_url) is not str:
        raise ValueError("Explicit private tile origin required")
    parsed = urlsplit(tile_url)
    try:
        local = ipaddress.ip_address(parsed.hostname or "").is_loopback
        port = parsed.port
    except ValueError:
        raise ValueError("Explicit private tile origin required") from None
    if (
        parsed.scheme != "http"
        or not local
        or port is None
        or not 1 <= port <= 65535
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or any(c.isspace() or ord(c) < 32 or c == "\\" for c in tile_url)
    ):
        raise ValueError("Explicit private tile origin required")
    source = original.decode("utf-8")
    for before in (BUILD_BEFORE, INTERESTING_BEFORE):
        if source.count(before) != 1:
            raise ValueError("Native renderer membership boundary changed")
    patched = source.replace(BUILD_BEFORE, BUILD_AFTER).replace(
        INTERESTING_BEFORE, INTERESTING_AFTER
    )
    old_url = "http://ogma.lti.cs.cmu.edu:8080/tile/"
    if patched.count(old_url) != 2:
        raise ValueError("Original native tile URL boundary changed")
    return patched.replace(old_url, tile_url + "/tile/")

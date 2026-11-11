"""Exact reviewed native UI refresh and passive real membership reader.

Pure bytes-to-text transform; no writes or browser actions.
"""

import hashlib

PINNED = {
    "index.js": "10dd34fa707fa45b795c07c1070bd38c368e4c37e63825ca1b5ec93101e74424",
    "leaflet.share.js": "69e60af41fd672f84f919d72255465c46711cad2f1778b80cca8be3e50e7beba",
    "leaflet.layers.js": "54608669c8498eec2f834a92058ceb869f78b51b02249fd52161d00123b94228",
}

GUARD = '      if (event && (event.type === "layeradd" || event.type === "layerremove") &&\n          event.layer && (!event.layer.options || (!event.layer.options.code && !event.layer.options.keyid)) &&\n          map.dataLayer.hasLayer(event.layer)) return;\n'

MAP_CONSTRUCTOR = '  var map = new L.OSM.Map("map", {\n    zoomControl: false,\n    layerControl: false,\n    contextmenu: true,\n    worldCopyJump: true\n  });'

MEMBERSHIP_READER = '\n  Object.defineProperty(window, "__labNativeLayerState", {\n    configurable: false, writable: false,\n    value: function () {\n      return {"Map Data": map.hasLayer(map.dataLayer),\n              "Map Notes": map.hasLayer(map.noteLayer)};\n    }\n  });\n'


def frontend_source(name: str, original: bytes) -> str:
    if (
        type(name) is not str
        or name not in PINNED
        or type(original) is not bytes
        or hashlib.sha256(original).hexdigest() != PINNED[name]
    ):
        raise ValueError("Exact reviewed native UI source bytes required")
    source = original.decode("utf-8")
    if name == "index.js":
        before = '  map.on("moveend layeradd layerremove", function () {\n'
        after = '  map.on("moveend layeradd layerremove", function (event) {\n' + GUARD
        count = 1
    elif name == "leaflet.share.js":
        before = "    function update() {\n"
        after = "    function update(event) {\n" + GUARD
        count = 1
    else:
        before = 'map.on("layeradd layerremove", function () {\n'
        after = 'map.on("layeradd layerremove", function (event) {\n' + GUARD
        count = 2
    if source.count(before) != count:
        raise ValueError("Native callback boundary changed")
    patched = source.replace(before, after)
    if name == "index.js":
        if patched.count(MAP_CONSTRUCTOR) != 1:
            raise ValueError("Pinned actual Map constructor missing")
        patched = patched.replace(MAP_CONSTRUCTOR, MAP_CONSTRUCTOR + MEMBERSHIP_READER)
    return patched

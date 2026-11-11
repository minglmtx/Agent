"""Exact selected native frontend transforms; preserve native cap/render order."""

import hashlib
from lab_generate_skill.domain.map_frontend import (
    FRONTEND_FILES,
    MapFrontendPlan,
    MapFrontendChange,
)
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.domain.release import ReleaseFile
from .native_frontend_source import frontend_source, PINNED as UI_PINS
from .native_renderer_source import renderer_source, PINNED_SHA256 as RENDERER_PIN

PINS = {
    **{"app/assets/javascripts/" + name: pin for name, pin in UI_PINS.items()},
    "vendor/assets/leaflet/leaflet.osm.js": RENDERER_PIN,
    "app/assets/javascripts/index/browse.js": "231693b5a51b110ddc2ed6b23efec42f12bcd4b772633105bd96a62a22b8a5d8",
    "app/assets/javascripts/index/notes.js": "0a9f7b461a5bd8f6bf156962911fca52b92b767a4365f2c6aef7e842c7425d8e",
    "app/controllers/api/map_controller.rb": "ed5cdb7ffee81b4243e74af2b3eceb1df4761a367ad216826dc5a3344c8c3234",
    "app/views/api/map/index.xml.builder": "5dd227104293e179e1e9d80e6a11dd02190b60465a4b1dd5a132cd69a4935df5",
    "lib/bounding_box.rb": "3288a9374ba0b56dde1f746d4012f1c09d1ab7af5a0e24f5893e9b9936e87ee1",
    "lib/osm.rb": "3a9f055151d1de5cda9a2fc098b3740fe8c14267d687dbb391031f7688d5ee79",
    "app/models/concerns/geo_record.rb": "62006ab8d4a75eb65cf32f4750fc075a2a7e32efbec70872676cebf834b6901b",
    "config/settings.yml": "e2b09431b4198801cfe7fe99fc3f26e4acdf3734b3d8aece94ecc25c40000cdb",
    "app/assets/javascripts/leaflet.map.js": "4ef82c58c2795849dc5cced90e3d0010450c7c953e842a86a39060009de1f743",
    # First byte pin4800560; old4795430 recorded size/mtime/mode, not this hash.
    "app/assets/javascripts/index/directions/fossgis_osrm.js": "95c832226ed4899a684f18b177db232183299f186d266548b5c16589c9501257",
}
PRELOAD = """
      # Verified association preloading; keep native rendering and record order.
      ActiveRecord::Associations::Preloader.new(:records => @nodes, :associations => { :changeset => :user }).call
      ActiveRecord::Associations::Preloader.new(:records => @ways, :associations => [{ :changeset => :user }, :nodes]).call
      ActiveRecord::Associations::Preloader.new(:records => @relations, :associations => [:relation_tags, :relation_members, { :changeset => :user }]).call
"""


def preparation(spec: MapServiceSpec, originals: dict[str, bytes]) -> MapFrontendPlan:
    spec = MapServiceSpec.model_validate(spec)
    if type(originals) is not dict or set(originals) != FRONTEND_FILES:
        raise ValueError("Complete selected fourteen original frontend files required")
    for name, body in originals.items():
        if (
            type(body) is not bytes
            or not body
            or len(body) > 1024 * 1024
            or hashlib.sha256(body).hexdigest() != PINS[name]
        ):
            raise ValueError(
                "Exact selected original frontend source required: " + name
            )
    changed = {
        "app/assets/javascripts/"
        + name: frontend_source(
            name, originals["app/assets/javascripts/" + name]
        ).encode()
        for name in UI_PINS
    }
    renderer = "vendor/assets/leaflet/leaflet.osm.js"
    changed[renderer] = renderer_source(
        originals[renderer], f"http://127.0.0.1:{spec.ports.tiles}"
    ).encode()
    controller = "app/controllers/api/map_controller.rb"
    source = originals[controller].decode()
    anchor = "      @relations.uniq!\n"
    if source.count(anchor) != 1:
        raise ValueError("Original export preload boundary differs")
    changed[controller] = source.replace(anchor, anchor + PRELOAD).encode()
    engine = "app/assets/javascripts/index/directions/fossgis_osrm.js"
    source = originals[engine].decode()
    for profile, old in (("car", "5000"), ("bike", "5001"), ("foot", "5002")):
        needle = '"' + profile + '": "' + old + '"'
        if source.count(needle) != 1:
            raise ValueError("Original routing port mapping differs")
        source = source.replace(
            needle, '"' + profile + '": "' + str(getattr(spec.ports, profile)) + '"'
        )
    changed[engine] = source.encode()
    leaflet = "app/assets/javascripts/leaflet.map.js"
    source = originals[leaflet].decode()
    old = 'window.location.protocol + "//" + window.location.hostname + "/go/"'
    if source.count(old) != 1:
        raise ValueError("Original short-link origin boundary differs")
    changed[leaflet] = source.replace(
        old, 'window.location.protocol + "//" + window.location.host + "/go/"'
    ).encode()
    pins = {
        name: ReleaseFile(
            path=name, sha256=PINS[name], size_bytes=len(body), executable=False
        )
        for name, body in sorted(originals.items())
    }
    return MapFrontendPlan(
        spec=spec,
        original=tuple(pins.values()),
        changes=tuple(
            MapFrontendChange(original=pins[name], content=body)
            for name, body in sorted(changed.items())
        ),
    )

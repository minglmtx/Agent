"""Small actual XML bytes, with ordered ways and legitimate external relations."""

from typing import Any

ROOT = ("0", "0", "0.5", "0.5")
LEFT = ("0", "0", "0.25", "0.5")
RIGHT = ("0.25", "0", "0.5", "0.5")
OBJECTS = (
    '<node id="1" version="2" lat="0.1" lon="0.1" timestamp="2024-01-01T00:00:00Z"><tag k="name" v="A"/></node>'
    '<node id="2" version="1" lat="0.2" lon="0.3"/>'
    '<way id="3" version="4"><nd ref="2"/><nd ref="1"/><tag k="highway" v="road"/></way>'
    '<relation id="4" version="1"><member type="way" ref="3" role=""/><member type="relation" ref="999" role="outer"/></relation>'
)


def xml(
    bounds: tuple[str, ...] = ROOT,
    objects: str = OBJECTS,
    *,
    generator: str = "OpenStreetMap server",
) -> bytes:
    west, south, east, north = bounds
    return (
        f'<osm version="0.6" generator="{generator}"><bounds minlon="{west}" minlat="{south}" maxlon="{east}" maxlat="{north}"/>'
        + objects
        + "</osm>"
    ).encode()


def leaves() -> list[tuple[tuple[str, ...], bytes]]:
    return [(LEFT, xml(LEFT)), (RIGHT, xml(RIGHT))]

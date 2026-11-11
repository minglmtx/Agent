"""Pure original complete-source and renderer rules; never a dispatch claim."""

from collections.abc import Mapping
from dataclasses import dataclass
import re
from urllib.parse import urlsplit
from .native_frontend_source import PINNED, frontend_source
from .native_renderer_source import renderer_source

RENDERER_READ = """() => {
                const p=window.L && L.OSM && L.OSM.DataLayer && L.OSM.DataLayer.prototype;
                if(!p)return null;
                return Object.fromEntries(["buildFeatures","interestingNode"].map(n=>
                    [n,typeof p[n]==="function"?Function.prototype.toString.call(p[n]):null]));
            }"""


def executable_source(source: str) -> str:
    if type(source) is not str or not source:
        raise ValueError("Complete executable source text required")
    return "\n".join(
        line
        for line in source.splitlines()
        if not re.fullmatch(r"//=\s*require(?:_self)?(?:\s+.*)?", line)
    ).strip()


@dataclass(frozen=True)
class NativeServedExpectation:
    sources: tuple[tuple[str, str], ...]
    renderer_functions: tuple[tuple[str, str], ...]


def reviewed_sources(
    originals: Mapping[str, bytes], tile_url: str
) -> NativeServedExpectation:
    if not isinstance(originals, Mapping) or set(originals) != {
        *PINNED,
        "leaflet.osm.js",
    }:
        raise ValueError("Exactly the four original native sources required")
    sources = {
        name: executable_source(frontend_source(name, originals[name]))
        for name in PINNED
    }
    renderer = renderer_source(originals["leaflet.osm.js"], tile_url)
    sources["leaflet.osm.js"] = executable_source(renderer)
    patterns = {
        "buildFeatures": r"  buildFeatures: (function.*?\n  }),",
        "interestingNode": r"  interestingNode: (function.*?\n  })\n\}\);",
    }
    functions = []
    for name, pattern in patterns.items():
        values = re.findall(pattern, renderer, re.S)
        if len(values) != 1:
            raise ValueError("Exact private native renderer function boundary changed")
        functions.append((name, values[0]))
    return NativeServedExpectation(tuple(sources.items()), tuple(functions))


def candidate_names(url: str) -> tuple[str, ...]:
    if type(url) is not str:
        raise ValueError("Original browser script URL required")
    path = urlsplit(url).path
    names = tuple(
        name
        for name in (*PINNED, "leaflet.osm.js")
        if re.search(
            r"/" + re.escape(name[:-3]) + r"(?:\.debug)?(?:-[0-9a-f]+)?\.js$", path
        )
    )
    if re.search(r"/application(?:\.debug)?(?:-[0-9a-f]+)?\.js$", path):
        return ("leaflet.osm.js",)
    return names


def matched_sources(
    expectation: NativeServedExpectation, body: bytes
) -> tuple[str, ...]:
    if type(body) is not bytes:
        raise ValueError("Complete actual browser response bytes required")
    text = body.decode("utf-8")
    return tuple(name for name, source in expectation.sources if source in text)

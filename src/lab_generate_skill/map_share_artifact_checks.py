"""Candidate result predicates for native Map sharing artifacts.

These functions check terminal output against an independently established
starting-state reference. They do not certify a browser roundtrip, website
availability, or task admission. A view shortlink is never a route proof.
"""
import math
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from .map_initial_view_link import local_link
from .map_route_initialization_binding import initial_url_state
from .map_route_normal_capture import exact_pair


def _local(value, origin):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError('An explicit local artifact URL is required')
    if any(ord(c) < 32 for c in value) or '\\' in value:
        raise ValueError('Invalid artifact URL characters')
    target, base = urlsplit(value), urlsplit(origin)
    if (target.scheme not in ('http', 'https') or not base.netloc
            or (target.scheme, target.netloc) != (base.scheme, base.netloc)
            or target.username is not None or target.password is not None):
        raise ValueError('Artifact must belong to the exact current instance')
    return target


def route_link(value, *, origin, expected_pair, expected_mode):
    """Require both ordered endpoints and travel mode in a native directions URL."""
    try:
        target = _local(value, origin)
        pair, mode = initial_url_state(target._replace(scheme='', netloc='').geturl())
        fragment = parse_qs(target.fragment, keep_blank_values=True)
        if set(fragment) - {'map', 'layers'} or any(len(v) != 1 for v in fragment.values()):
            return False
        if 'map' in fragment:
            from .map_local_capabilities import map_triplet
            map_triplet(value)
        return mode == expected_mode and exact_pair(pair, expected_pair)
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


def short_route_link(value, *, origin, expected_pair, expected_mode):
    """Check a local compact route's public identity before native reopening.

    The token alone is insufficient for success: the terminal evaluator must
    independently reopen this exact URL and check the actual native route.
    """
    from .map_short_route import decode
    try:
        target = _local(value, origin)
        query = parse_qs(target.query, keep_blank_values=True)
        if (not re.fullmatch(r'/go/[A-Za-z0-9_~@-]+', target.path)
                or target.fragment or set(query) != {'local_route'}
                or len(query['local_route']) != 1):
            return False
        pair, mode = decode(query['local_route'][0])
        return mode == expected_mode and exact_pair(pair, expected_pair)
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


def view_link(value, *, origin, expected_center):
    """Reuse the existing Standard-layer initial-view predicate unchanged."""
    try:
        _local(value, origin)
        return local_link(value, origin, expected_center)
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


class _Embed(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.iframes = []
        self.unsupported = False

    def handle_starttag(self, tag, attrs):
        # Native Share markup also contains a larger-map link after the iframe.
        if tag not in ('iframe', 'br', 'small', 'a'):
            self.unsupported = True
        if tag == 'iframe':
            if len({name for name, _ in attrs}) != len(attrs):
                self.unsupported = True
            self.iframes.append(dict(attrs))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def embed_markup(value, *, origin, width, height, expected_bbox, expected_layer):
    """Check markup dimensions and its native embed resource, not a rendered map.

    expected_bbox must come from the declared, independently captured map area;
    it must never be inferred from the actor's returned embed URL.
    """
    try:
        if not isinstance(value, str) or type(width) is not int or type(height) is not int or min(width, height) <= 0:
            return False
        parser = _Embed()
        parser.feed(value)
        parser.close()
        if parser.unsupported or len(parser.iframes) != 1:
            return False
        frame = parser.iframes[0]
        # Accept native embed attributes, not executable or layout-overriding
        # additions that a sanitized readback would otherwise silently ignore.
        if set(frame)-{'width','height','src','frameborder','scrolling','marginheight','marginwidth','style'}:
            return False
        if 'style' in frame and not re.fullmatch(r'\s*border\s*:\s*(?:1px solid black|0(?:px)?(?: none)?)\s*;?\s*',frame['style']):
            return False
        if frame.get('width') != str(width) or frame.get('height') != str(height):
            return False
        target = _local(frame.get('src'), origin)
        if target.path != '/export/embed.html' or target.fragment:
            return False
        query = parse_qs(target.query, keep_blank_values=True)
        if set(query) != {'bbox', 'layer'} or any(len(v) != 1 for v in query.values()) or query['layer'] != [expected_layer]:
            return False
        actual = [float(x) for x in query['bbox'][0].split(',')]
        reference = [float(x) for x in expected_bbox]
        for bounds in (actual, reference):
            if (len(bounds) != 4 or not all(math.isfinite(x) for x in bounds)
                    or not -180 <= bounds[0] < bounds[2] <= 180
                    or not -90 <= bounds[1] < bounds[3] <= 90):
                return False
        return all(abs(a-b) <= 1e-7 for a, b in zip(actual, reference))
    except (ValueError, TypeError, KeyError, OverflowError):
        return False

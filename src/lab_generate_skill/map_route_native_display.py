"""Native directions coordinate formatting, conditional on an exact full request.

The native frontend keeps the full lat/lon in its routing request, but uses
Number.toFixed(OSM.zoomPrecision(...)) in the URL and public form. The map is
fit to the completed route afterward; final hash zoom is not the formatting
zoom. This is a representation check, never an endpoint identity check.
"""
from decimal import Decimal, ROUND_HALF_UP
import math
import re
from urllib.parse import parse_qs, urlsplit


def number_to_fixed(value, digits):
    """ECMAScript Number.toFixed for finite geographic Numbers, native 0..5.

    Decimal.from_float retains the actual IEEE-754 Number before rounding.
    Decimal(str(value)) would round 1.005 differently from JavaScript.
    """
    if type(digits) is not int or not 0 <= digits <= 5:
        raise ValueError('Native map coordinate formatting precision required')
    number = float(value)
    if not math.isfinite(number) or abs(number) > 180:
        raise ValueError('Finite native geographic coordinate required')
    if number == 0:
        number = 0.0  # JavaScript does not preserve a negative zero Number.
    return format(Decimal.from_float(number).quantize(
        Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP), f'.{digits}f')


def native_numeric_point(text, exact_point):
    """Accept exact coordinates or exactly reproduced native toFixed output.

    No distance tolerance is used. A rounded field alone never establishes
    identity; the caller must pin the actual request pair and full response.
    """
    from .map_route_normal_capture import point
    if not isinstance(text, str):
        return False
    tokens = [v.strip() for v in text.split(',')]
    if len(tokens) != 2:
        return False
    try:
        exact = point(exact_point)
        actual = point(tokens)
    except ValueError:
        return False
    if actual == exact:
        return True
    matches = [re.fullmatch(r'-?\d+(?:\.(\d+))?', token) for token in tokens]
    if any(m is None for m in matches):
        return False
    digits = [len(m.group(1) or '') for m in matches]
    return (digits[0] == digits[1] and 0 <= digits[0] <= 5
            and all(token == number_to_fixed(value, digits[0])
                    for token, value in zip(tokens, exact)))


def native_url_pair(url, profile, exact_pair):
    parsed = urlsplit(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    raw = params.get('route', [''])[0].split(';')
    return (parsed.path == '/directions' and set(params) == {'engine', 'route'}
            and params.get('engine') == ['fossgis_osrm_' + profile]
            and len(params.get('route', [])) == 1 and len(raw) == 2
            and all(native_numeric_point(text, p) for text, p in zip(raw, exact_pair)))


def verified_route_checks(spec, served, independent_body, state, url, *, pinned_pair):
    """Keep normal renderer checks; qualify rounding with complete native proof.

    A nearby request in the same display rounding cell is rejected by the exact
    pair comparison, even if it produces identical-looking route text. Native
    waypoints and every response field, rather than only the first route, must
    also match the independent full response.
    """
    from .map_route_normal_capture import complete_route, exact_pair, fingerprint
    from lab_generate_skill.map_route import route_checks, normalized
    if (served.get('complete_native_response') is not True
            or not exact_pair(served.get('pair'), pinned_pair)):
        raise ValueError('Exact complete actual native routing request required')
    expected = complete_route(independent_body)
    actual = complete_route(served.get('body'))
    if fingerprint(served['body']) != fingerprint(independent_body):
        raise ValueError('Complete actual native body differs from independent response')
    choices = [r for r in spec['alternatives'] if r['profile'] == served['profile']]
    if len(choices) != 1 or fingerprint(choices[0]['backend']) != fingerprint(expected):
        raise ValueError('Actual request transport and complete rendered reference disagree')
    checks = route_checks(spec, state, url)
    labels = spec.get('endpoint_labels')
    if labels is not None and (len(labels) != 2 or any(
            not isinstance(v, list) or not v or any(not isinstance(x, str) or not x for x in v)
            for v in labels)):
        raise ValueError('Complete independently verified endpoint names required')
    fields = [state['origin'], state['destination']]
    fields_match = all(native_numeric_point(text, p) or labels is not None
        and normalized(text).casefold() in {normalized(x).casefold() for x in names}
        for text, p, names in zip(fields, pinned_pair, labels or [[], []]))
    form_absent = state.get('route_form_visible') is False and all(
        state[k] == '' for k in ('origin', 'destination', 'engine'))
    if form_absent:
        fields_match = (checks['route_transport_mode'] and checks['route_rendered_content']
                        and checks['route_line_displayed'])
    checks['route_endpoints'] = bool(native_url_pair(url, served['profile'], pinned_pair)
                                     and fields_match)
    return checks

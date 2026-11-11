"""Candidate print-artifact checks using a full independent native route.

The caller must separately bind the reference to the published task, initial
state and dataset. This module grants no admission. It checks the document at
print time, rather than a subsequently displayed route or the actor's answer.
"""
from copy import deepcopy
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit

from .browser_print import pdf_text
from .map_route_normal_capture import complete_route, exact_pair, fingerprint, terminal_checks


def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', text).split())


def full_turns_printed(pages, rows):
    if (not isinstance(rows, list) or not rows or
            any(not isinstance(r, str) or not r.strip() for r in rows)):
        raise ValueError('Independent full native turn rows required')
    text = normalized('\n'.join(pages))
    values = [normalized(row) for row in rows]
    for index, value in enumerate(values, 1):
        if not re.match(r'^' + str(index) + r'\.\s', value):
            raise ValueError('Independent native turn numbers are incomplete')
    cursor = 0
    for value in values:
        # Preserve every maneuver, road name, distance and ordering. Only
        # layout whitespace differs; "1." must not match a suffix of "11.".
        match = re.search(r'(?<!\w)' + re.escape(value) + r'(?!\w)', text[cursor:])
        if match is None:
            return False
        cursor += match.end()
    return True


def require_reference(reference):
    body = reference['native_body']
    route = complete_route(body)
    if (reference.get('independent_native_read') is not True
            or reference.get('native_body_sha256') != fingerprint(body)
            or not exact_pair(reference['pair'], reference['scope']['pinned_request_pair'])):
        raise ValueError('Independent full native route reference is unbound')
    choices = [r for r in reference['scope']['rendered_route_spec']['alternatives']
               if r['profile'] == reference['profile']]
    if len(choices) != 1 or fingerprint(choices[0]['backend']) != fingerprint(route):
        raise ValueError('Native displayed reference differs from backend')
    rows = choices[0]['native']['rows']
    if len(rows) != len(route['legs'][0]['steps']):
        raise ValueError('Independent route omits turn rows')
    full_turns_printed([], rows)  # Validate numbering independently of actor artifacts.
    return rows


def evaluate_artifact(body, receipt, source, reference, *, site_origin):
    checks = {}
    def result(status, reason):
        return dict(version='native-route-print-candidate-v1', status=status,
                    reward=None if status == 'unknown' else float(status == 'success'),
                    checks=checks, reason=reason)
    try:
        rows = require_reference(reference)
        if (receipt.get('status') != 'completed' or receipt.get('renderer') != 'chromium-page-pdf'
                or receipt.get('source_sha256') != hashlib.sha256(json.dumps(source,
                    sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                or receipt.get('source_url') != source['url']
                or receipt.get('sha256') != hashlib.sha256(body).hexdigest()
                or receipt.get('bytes') != len(body)):
            raise ValueError('Print artifact or print-time source receipt is unavailable')
        pages = pdf_text(body)
        if len(pages) != receipt.get('page_count'):
            raise ValueError('Saved print page count differs from its receipt')
        actual, expected = urlsplit(source['url']), urlsplit(site_origin)
        checks['local_directions_printed'] = ((actual.scheme, actual.netloc) ==
            (expected.scheme, expected.netloc) and actual.path == '/directions')
        if not checks['local_directions_printed']:
            return result('failure', 'The printed document is not the requested local route page.')
        native = source['native']
        state = native['state']
        if state.get('loading') is not False:
            return result('unknown', 'The route was still loading when printed.')
        if state.get('route_visible') is False:
            return result('failure', 'The printed page contains no displayed route.')
        if native.get('capture_error'):
            return result('unknown', 'Native print-time route evidence is incomplete.')
        requests = native['responses']
        if not isinstance(requests, list):
            raise ValueError('Print-time native response list unavailable')
        if not requests:
            return result('unknown', 'A displayed route lacks its native response capture.')
        matches = [r for r in requests if r.get('complete_native_response') is True
            and r.get('profile') == reference['profile']
            and exact_pair(r.get('pair'), reference['pair'])]
        checks['requested_native_route_observed'] = bool(matches)
        if not matches:
            return result('failure', 'The requested native route was not observed before printing.')
        candidates = [terminal_checks(reference['scope'], served, reference['native_body'],
                                      state, source['url']) for served in matches]
        selected = next((r for r in candidates if all(r.values())), candidates[-1])
        checks.update(selected)
        checks['every_turn_printed_in_order'] = full_turns_printed(pages, rows)
        return result('success' if all(checks.values()) else 'failure',
                      'Checked the saved PDF and its complete print-time native route.')
    except (KeyError, TypeError, ValueError, OSError, ImportError):
        return result('unknown', 'Print artifact, native source or independent reference is incomplete.')


def capture_source(page, capture):
    """Passive print-time snapshot. No routing request or browser action added."""
    from .map_route import read_route
    return dict(state=read_route(page), responses=deepcopy(capture.responses),
                capture_error=deepcopy(capture.latest_error))

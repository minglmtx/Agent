"""Preserve declared export starts without navigating on the actor's behalf."""
from urllib.parse import urlsplit

from . import map_export_normal as normal
from .browser_http_status import terminal_document_evidence, is_error_document


def capture_initial(page, contract, *, site_origin=None):
    spec = normal.validate(contract)
    actual, start = urlsplit(page.url), urlsplit(contract['start_path'])
    if (actual.path, actual.query) != (start.path, start.query):
        raise RuntimeError('Original first native document changed')
    policy = spec.get('initial_document_policy', 'native_map')
    evidence = None
    if policy == 'native_document':
        # This opt-in is part of the fingerprinted task contract. It permits
        # a healthy document, not a missing initial map for map-relative goals.
        if not site_origin:
            raise RuntimeError('Owned website origin required for document initialization')
        origin = urlsplit(site_origin)
        if (actual.scheme, actual.netloc) != (origin.scheme, origin.netloc):
            raise RuntimeError('Initial document belongs to another website')
        if actual.fragment != start.fragment:
            raise RuntimeError('Declared initial document fragment changed')
        evidence = terminal_document_evidence(page)
        status = evidence.get('http_status')
        if (type(status) is not int or not 200 <= status < 300
                or is_error_document(page.url, status, page.title())):
            raise RuntimeError('Healthy original native document not confirmed')
    else:
        from .map_view import wait_native_view
        wait_native_view(page, contract['start_path'])
    snapshot = normal.read_snapshot(page)
    if snapshot['url'] != page.url:
        raise RuntimeError('Initial document changed during capture')
    if policy == 'native_map' and snapshot['view'].get('map_visible') is not True:
        raise RuntimeError('Original public native map unavailable')
    if evidence is not None:
        if evidence['url'] != snapshot['url']:
            raise RuntimeError('Initial document changed after HTTP capture')
        snapshot['initial_document_evidence'] = evidence
    return snapshot

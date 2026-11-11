"""Compose pre-request provider evidence with full native OSM-file verification.

This is an evaluator primitive, not a task admission or a default runtime entry.
Provider state/receipts must be captured into the normal transport snapshot
before an export request. Terminal provider state cannot repair earlier evidence.
"""
from copy import deepcopy

from . import map_export_normal as normal
from .map_provider_observation import READER
from .map_provider_terminal import evaluate_provider_terminal

VERSION = 'map-provider-before-osm-export-v1'


def _artifact_contract(contract):
    # Internal sub-predicate only. This projection never grants task admission.
    return {k:v for k,v in contract.items() if k != 'ordered_export'}


def validate(contract):
    spec = contract.get('ordered_export')
    if spec != dict(version=VERSION, provider='hot', initial_provider='M',
                    retain_initial_area=False, retain_initial_route=False):
        raise ValueError('Explicit Standard-to-Humanitarian then OSM export contract required')
    export = normal.validate(_artifact_contract(contract))
    if export['kind'] != 'osm_download' or export['area_policy'] != 'actor_selected':
        raise ValueError('Original ordered export has no extra original-area requirement')
    return spec


def fingerprint(contract):
    validate(contract)
    return normal.digest(dict(export=normal.fingerprint(_artifact_contract(contract)), ordered_export=contract['ordered_export']))


def observe_provider(page, snapshot, response_hashes, document):
    """Private observation only; no clicks, navigation, retries or target hints."""
    if document.get('url') != page.url or snapshot.get('url') != page.url:
        raise ValueError('Provider and export observations must share the actual page')
    result = deepcopy(snapshot)
    result['ordered_export_provider'] = dict(
        state=deepcopy(page.evaluate(READER)), response_sha256=deepcopy(response_hashes),
        document=deepcopy(document))
    return result


def evaluate(contract, page, answer, initial, current, reference, *, site_origin,
             download, transport_event, initial_provider, server,
             integrity=True, runtime_error=None):
    spec = validate(contract)
    checks = {}

    def result(status, reason):
        return dict(version=VERSION, status=status,
                    reward={'success':1., 'failure':0., 'unknown':None}[status],
                    checks=checks, reason=reason)

    if runtime_error or integrity is not True:
        return result('unknown', 'Runtime or state integrity is not verified.')
    if (not isinstance(initial_provider, dict)
            or [x.get('code') for x in initial_provider.get('active', [])] != ['M']):
        return result('unknown', 'Declared initial Standard layer is not verified.')
    if download is None:
        base = normal.evaluate(_artifact_contract(contract), page, answer, initial, current, reference,
                               site_origin=site_origin)
        checks.update(base['checks'])
        return result(base['status'], 'No completed native export artifact.')
    event = transport_event
    try:
        # Both the captured selection and provider state belong to this exact
        # request/file; same URL alone is not a sufficient identity.
        order = [event['request_sequence'], event['response']['sequence'], event['sequence']]
        if (event['native'] is not True or event['selection_observed_before_request'] is not True
                or any(type(x) is not int or x <= 0 for x in order)
                or not order[0] < order[1] < order[2]
                or event['download_id'] != download['metadata']['download_id']
                or event['url'] != download['metadata']['url']
                or any(event['response'][k] != download['metadata'][k]
                       for k in ('http_status', 'content_type', 'content_disposition'))):
            raise ValueError('Request/file identity differs')
        selection = event['selection_snapshot']
        provider = selection['ordered_export_provider']
        state, receipts = provider['state'], provider['response_sha256']
        observed_page = provider['document']
        if (not isinstance(state, dict) or not isinstance(receipts, dict)
                or not isinstance(observed_page, dict) or observed_page.get('url') != selection['url']):
            raise ValueError('Provider capture missing')
    except (KeyError, TypeError, ValueError):
        return result('unknown', 'Pre-request provider or download identity capture unavailable.')
    base = normal.evaluate(_artifact_contract(contract), page, answer, initial, current, reference,
                           site_origin=site_origin, download=download, selection=selection)
    checks.update(base['checks'])
    if base['status'] != 'success':
        return result(base['status'], 'The exported artifact does not satisfy native OSM checks.')
    # Evaluate the observed pre-request frame at its own actual geographic
    # position. Original goal does not require retaining the initial route/area.
    provider_result = evaluate_provider_terminal(dict(family='base_layer', provider=spec['provider'],
        retain_initial_area=False, retain_initial_route=False), initial=initial_provider,
        terminal=state, page=observed_page, site_origin=site_origin,
        server=server, response_hashes=receipts)
    checks.update({'before_export_'+k:v for k,v in provider_result['checks'].items()})
    checks['export_request_order_verified'] = True
    return result(provider_result['status'], provider_result['reason'])


def feedback(judgment):
    if judgment.get('version') != VERSION:
        raise ValueError('Ordered export judgment required')
    return dict(status=judgment['status'], reward=judgment['reward'],
        checks=[dict(condition=k, passed=v) for k,v in judgment['checks'].items() if type(v) is bool],
        private_reference_values_provided=False, action_sequence_provided=False)

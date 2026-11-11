"""Shared route component checks against independently bound native responses.

These produce references for later full-environment acceptance. They do not
admit tasks and never take endpoint identities from an actor's choices.
"""
from .map_route_normal_capture import complete_route, exact_pair, fingerprint
from .map_route_native_display import verified_route_checks
import time


def wait_for_native_capture(page, capture, pair, profile, timeout_seconds=10):
    """Pump browser events until the requested full response has been persisted.

    A rendered route/jQuery idle state can precede completion of the Python
    response.body() callback. Never replace missing capture with visible text.
    This barrier observes the response; it performs no navigation or actions.
    """
    if not 0 < timeout_seconds <= 30:
        raise ValueError('Capture deadline must be positive and bounded')
    deadline = time.monotonic() + timeout_seconds
    while True:
        if capture.first_error:
            raise ValueError('Native route response capture failed')
        if capture.responses:
            latest = capture.responses[-1]
            if (latest.get('complete_native_response') is True
                    and latest.get('profile') == profile
                    and exact_pair(latest.get('pair'), pair)):
                return latest
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Requested full native route response was not captured')
        page.wait_for_timeout(min(50, remaining * 1000))


def evaluate_rendered_candidate(pair, profile, body, reference_state, served, state, url, *, endpoint_labels=None):
    complete_route(body)
    checks = {
        'complete_actual_response': bool(served and served.get('complete_native_response') is True),
        'exact_requested_endpoints': bool(served and exact_pair(served.get('pair'), pair)),
        'requested_mode': bool(served and served.get('profile') == profile),
        'independent_body_matches': bool(served and fingerprint(served.get('body')) == fingerprint(body)),
    }
    if not all(checks.values()):
        return checks
    # Legacy display checks use numeric pairs; retain exact decimal request
    # strings above and in pinned_pair for the independent identity check.
    spec = dict(pair=[[float(v) for v in p] for p in pair],
                alternatives=[dict(profile=profile, backend=complete_route(body), native=reference_state)])
    if endpoint_labels is not None:
        spec['endpoint_labels'] = endpoint_labels
    checks.update(verified_route_checks(spec, served, body, state, url, pinned_pair=pair))
    return checks


def resolved_candidates(candidates, geocodes, geometry=None):
    """Recompute all endpoint variants from full archived identity evidence."""
    from .map_route_candidate_batch import backend_spec, candidate_pairs
    from .map_native_identity_declarations import declare_query
    geometry = {} if geometry is None else geometry
    rows = []
    used_geometry = set()
    for candidate in candidates:
        spec = backend_spec(candidate)
        if spec['endpoint_request']['kind'] == 'replace_one_endpoint':
            from .map_geometry_endpoint_alternatives import replacement_variants
            query = spec['endpoint_request']['query']
            if query not in geometry:
                raise ValueError('Destination replacement requires reviewed full geometry evidence')
            evidence = geometry[query]
            if not isinstance(evidence.get('raw_body'), str):
                raise ValueError('Original native geometry response text required')
            spec, variants, declaration = replacement_variants(
                candidate, geocodes[query], evidence['receipt'], evidence['raw_body'].encode('utf-8'))
            rows.append(dict(candidate=candidate, spec=spec, variants=variants,
                             geometry_declaration=declaration))
            used_geometry.add(query)
            continue
        if spec['endpoint_request']['kind'] != 'named_places':
            raise ValueError('This batch requires named endpoints, not an implicit initial route')
        queries = spec['endpoint_request']['queries']
        evidence = {q: geocodes[q] for q in queries}
        reviews = {q: declare_query(q, evidence[q]) for q in queries}
        variants = candidate_pairs(spec, {'geocodes': evidence}, reviews)
        rows.append(dict(candidate=candidate, spec=spec, variants=variants))
    if set(geometry) != used_geometry:
        raise ValueError('Unbound geometry evidence must not be included in the route batch')
    return rows

"""Existential native directions checks for tasks with freely chosen endpoints.

Only terminal state is scored. Endpoint selection is permitted by the original
goal; the chosen points are not used to recover an unspecified fixed target.
The evaluator independently obtains complete native routing data and a separate
normal rendered reference. A prior completed route cannot validate a new,
unsubmitted form, and no private endpoint or answer is supplied to the actor.
"""
from copy import deepcopy
import re
from .map_route_normal_capture import complete_route, exact_pair, fingerprint, point


class IndependentReferenceUnavailable(RuntimeError):
    """Native/evaluator transport failure, never converted to actor failure."""

VERSION = 'native-open-route-choice-v1'
PROTOCOL = {
    'version': VERSION,
    'completion_boundary': 'actual_submitted_distinct_native_endpoints_and_complete_current_route',
    'original_endpoint_choice_preserved': True,
    'fixed_hidden_endpoint_answer_added': False,
    'independent_terminal_native_and_normal_render_reference_required': True,
    'original_model_judge_equivalence_claimed': False,
}


def validate_contract(contract):
    request = contract.get('endpoint_request')
    if (not isinstance(request, dict) or request.get('kind') != 'two_actor_chosen_distinct_points'
            or request.get('normal_completion_protocol') not in (None, PROTOCOL)
            or request.get('no_op_default_route_not_accepted') is not True
            or request.get('both endpoint identities and actual submitted pair required') is not True
            or type(request.get('exact numeric points required')) is not bool
            or contract.get('completion_kind') != 'displayed_route'
            or contract.get('optimization_scope')
            or not isinstance(contract.get('allowed_modes'), list) or not contract['allowed_modes']
            or any(m not in ('car', 'bike', 'foot') for m in contract['allowed_modes'])
            or len(set(contract['allowed_modes'])) != len(contract['allowed_modes'])):
        raise ValueError('Original free endpoint scope and any declared completion protocol must agree')
    return request


def distinct_pair(pair):
    return isinstance(pair, list) and len(pair) == 2 and point(pair[0]) != point(pair[1])


def _valid_sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _form_field_verified(value, requested_point, evidence, *, numeric_only):
    from .map_route_native_display import native_numeric_point
    if native_numeric_point(value, requested_point):
        return True
    if numeric_only or not isinstance(value, str) or not value.strip():
        return False
    if (not isinstance(evidence, dict) or evidence.get('actual_public_field_value') != value
            or evidence.get('independent_native_query_read') is not True
            or not _valid_sha(evidence.get('complete_native_query_receipt_sha256'))
            or not isinstance(evidence.get('full_native_records'), list)
            or evidence.get('full_native_records_sha256') != fingerprint(evidence['full_native_records'])):
        return False
    # An open-choice task permits selecting one of several native objects.
    # The exact actual OSRM request identifies the selection; rank is irrelevant.
    for row in evidence['full_native_records']:
        if (not isinstance(row, dict) or type(row.get('osm_id')) is not int or row['osm_id'] <= 0
                or row.get('osm_type') not in ('node', 'way', 'relation') or not row.get('display_name')):
            continue
        try:
            if point([row['lat'], row['lon']]) == point(requested_point):
                return True
        except (KeyError, TypeError, ValueError):
            continue
    return False


def terminal_checks(contract, served, reference, state, current_url, field_evidence):
    request = validate_contract(contract)
    body = complete_route(served['body'])
    expected = complete_route(reference['native_body'])
    if (reference.get('independent_native_read') is not True
            or reference.get('independent_normal_browser') is not True
            or not _valid_sha(reference.get('native_reference_receipt_sha256'))
            or reference.get('native_body_sha256') != fingerprint(reference['native_body'])
            or not exact_pair(served['pair'], reference.get('pair'))
            or served['profile'] != reference.get('profile')
            or not isinstance(reference.get('rendered_state'), dict)):
        raise ValueError('Independent complete exact native and normal rendered reference required')
    if not isinstance(field_evidence, list) or len(field_evidence) != 2:
        raise ValueError('Both actual public endpoint fields require explicit verification')
    fields = [state.get('origin'), state.get('destination')]
    visible = state.get('route_form_visible') is True
    numeric = request['exact numeric points required']
    field_checks = [_form_field_verified(v, p, e, numeric_only=numeric)
                    for v, p, e in zip(fields, served['pair'], field_evidence)]
    form_absent = state.get('route_form_visible') is False and fields == ['', '']
    # A source explicitly requiring coordinate entry retains a numeric-field
    # requirement. Other open tasks can complete after the native sidebar hides.
    form_ok = visible and all(field_checks) or form_absent and not numeric
    from .map_route_native_display import verified_route_checks
    spec = {'pair': [[float(x) for x in point(p)] for p in served['pair']],
            'alternatives': [{'profile': served['profile'], 'backend': deepcopy(expected),
                              'native': deepcopy(reference['rendered_state'])}],
            'endpoint_labels': [[v] if isinstance(v, str) and v else ['native endpoint'] for v in fields]}
    checks = {
        'actual_distinct_chosen_endpoints': distinct_pair(served['pair']),
        'actual_positive_distance_between_native_locations': body['distance'] > 0,
        'requested_transport_mode': served['profile'] in contract['allowed_modes'],
        'complete_actual_native_body_independently_equal': fingerprint(served['body']) == fingerprint(reference['native_body']),
        'actual_public_fields_identify_the_submitted_endpoints': bool(form_ok),
    }
    checks.update(verified_route_checks(spec, served, reference['native_body'],
        state, current_url, pinned_pair=reference['pair']))
    return checks


class OpenRouteChoiceEvaluator:
    """Read-only independent-reference provider, called after the actor stops.

    The callback must use the current protected native factory, not an actor
    page as its reference. Complete bodies and separate normal rendered records
    remain evaluator artifacts. No actor action is retried or altered.
    """
    def __init__(self, contract, *, reference_provider, field_provider):
        self.contract = deepcopy(contract)
        validate_contract(self.contract)
        self.reference_provider = reference_provider
        self.field_provider = field_provider
        self.cache = {}

    def evaluate(self, capture, state, current_url, health):
        outcomes = []
        reference_errors = []
        if not isinstance(state,dict) or not isinstance(current_url,str):
            return {'version':VERSION,'status':'unknown','reward':None,'checks':health,
                    'reason':'Actual normal terminal route observation is missing'}
        if not isinstance(capture,list):
            return {'version':VERSION,'status':'unknown','reward':None,'checks':health,
                    'reason':'Actual passive native request history is missing'}
        for served in reversed(capture):
            if served.get('complete_native_response') is not True:
                continue
            try:
                pair = served['pair']
                if not distinct_pair(pair):
                    continue
                if served['profile'] not in self.contract['allowed_modes']:
                    continue
                # Filter old exploratory routes before performing any private
                # read. This URL check alone never grants task completion.
                from urllib.parse import parse_qs, urlsplit
                from .map_route_native_display import native_url_pair
                url=urlsplit(current_url);params=parse_qs(url.query)
                raw=params.get('route', [''])[0].split(';')
                if not native_url_pair(current_url, served['profile'], pair):
                    continue
                key = fingerprint({'pair': pair, 'profile': served['profile'], 'body': served['body']})
                if key not in self.cache:
                    self.cache[key] = self.reference_provider(pair, served['profile'])
                fields = self.field_provider(state, pair)
                checks = terminal_checks(self.contract, served, self.cache[key], state, current_url, fields)
                checks.update(health)
            except IndependentReferenceUnavailable as error:
                reference_errors.append({'type':type(error).__name__,'message':str(error)})
                continue
            except ValueError:
                # An intermediate wrong/unfinished choice is ordinary exploration.
                continue
            success = all(v is True for v in checks.values())
            outcomes.append({'version': VERSION, 'status': 'success' if success else 'failure',
                             'reward': float(success), 'checks': checks})
            if success:
                return outcomes[-1]
        if reference_errors:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':health,
                    'reason':'Independent complete native/normal reference unavailable',
                    'reference_diagnostics':reference_errors}
        return outcomes[0] if outcomes else {'version': VERSION, 'status': 'failure', 'reward': 0.0,
                                            'checks': dict(health, actual_submitted_distinct_native_route=False)}

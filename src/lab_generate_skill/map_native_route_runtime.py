"""Source-bound routes through the common terminal-only native read lifecycle.

No navigation, strategy or golden route is sent to the actor. This bridge uses
the same native capture and evaluator that passed actual normal cold controls.
Published failed allocations remain failed; only complete passed source rows
from their genuinely independent factories may form a source admission.
"""
from copy import deepcopy
from pathlib import Path
import json
import re
from urllib.parse import urlsplit
from . import map_route_normal_runtime as routes
from .map_route_normal_capture import fingerprint
from .map_open_route_choice import VERSION as OPEN_CHOICE_VERSION

VERSION = 'map-native-route-common-dispatch-v1'
MARKER = {'version': VERSION}
FEEDBACK_VERSIONS = (routes.VERSION, OPEN_CHOICE_VERSION)

def enabled(contract):
    return isinstance(contract.get('map_native_route'), dict)

def validate(contract):
    if (not enabled(contract) or contract['map_native_route'] != MARKER
            or contract.get('domain') != 'map'
            or (contract.get('task_id') != contract.get('source_task_id')
                and not contract.get('training_initialization') and not contract.get('goal_revision'))
            or contract.get('heldout_quarantine') is not False
            or contract.get('eligible_for_training') is not False
            or contract.get('normal_admitted') is not False
            or contract.get('task_text_revision') is not None
            or (not contract.get('goal_revision')
                and contract.get('original_goal',contract.get('goal')) != contract.get('goal'))
            or (contract.get('initialization_revision') is not None
                and not contract.get('training_initialization') and not contract.get('goal_revision'))
            or any(contract.get(k) for k in ('query', 'map_native_layer', 'map_export',
                                             'map_zoom', 'map_geolocation'))):
        raise ValueError('Exact original source route and one common lifecycle required')
    if contract.get('goal_revision'):
        if contract['goal_revision'].get('version') == 'native-local-coverage-same-capability-derived-v1':
            from .map_local_coverage_goal_revision import validate as validate_goal_revision
        elif contract['goal_revision'].get('version') == 'explicit-missing-route-training-v1':
            from .map_missing_route_revision import validate as validate_goal_revision
        else:
            from .map_route_goal_revision_binding import validate as validate_goal_revision
        validate_goal_revision(contract)
    if contract.get('training_initialization'):
        from .map_route_initialization_binding import validate as validate_initialization
        validate_initialization(contract)
    return routes.source_binding(contract)

def require_admission(contract, proof):
    validate(contract)
    binding = routes.require_source_gate(contract, proof)
    source = contract['source_task_id']
    ids = proof.get('full_original_manifest_source_ids')
    if (proof.get('source_composition_version') != 'actual-source-route-proof-composition-v1'
            or not isinstance(ids, list) or not ids or ids != sorted(set(ids))
            or source not in ids
            or not re.fullmatch(r'[0-9a-f]{64}', str(proof.get('full_original_manifest_sha256', '')))):
        raise ValueError('Full original manifest and explicit source composition required')
    for index, row in enumerate(proof['normal_source_cycles']):
        actual = row.get('actual_cycle')
        if (not isinstance(actual, dict) or fingerprint(actual) != row.get('actual_cycle_sha256')
                or actual.get('cycle') != index
                or actual.get('full_original_manifest_source_ids') != ids
                or actual.get('source_count') != len(ids)
                or actual.get('batch_source_count') != len(actual.get('sources', []))
                or actual.get('initial_fingerprint') != proof['full_native_baseline']
                or actual.get('final_fingerprint') != proof['full_native_baseline']
                or actual.get('fresh_factory_id') != row.get('fresh_factory_id')
                or actual.get('full_lifecycle_passed') is not True
                or any(actual.get(k) is not True for k in routes.LIFECYCLE)
                or any(type(actual.get(k)) is not int or actual[k] != 0
                       for k in ('actor_attempts', 'api_calls', 'task_admissions'))
                or row.get('full_original_manifest_source_ids') != ids
                or row.get('full_original_manifest_sha256') != proof['full_original_manifest_sha256']):
            raise ValueError('Complete actual cold scope, hash, reset and protection required')
        passed = [r for r in actual['sources'] if r.get('source_task_id') == source]
        if (len(passed) != 1 or passed[0].get('normal_candidate_passed') is not True
                or fingerprint(passed[0]) != row.get('actual_source_row_sha256')
                or any(passed[0].get(k) != row.get(k) for k in
                       ('source_binding_sha256', 'controls', 'private_reference_set_sha256',
                        'private_reference_semantics_sha256', 'private_reference_artifact_file_sha256'))
                or any(type(row.get(k)) is not int or row[k] != 0 for k in ('actor_attempts', 'api_calls'))
                or row.get('actual_terminal_control_job_exit_code') !=
                   ('0:0' if row['actual_terminal_control_job_state'] == 'COMPLETED' else '2:0')
                or any(not re.fullmatch(r'[0-9a-f]{64}', str(row.get(k, ''))) for k in
                       ('actual_cycle_receipt_file_sha256', 'actual_allocation_file_sha256',
                        'executed_packet_sha256'))):
            raise ValueError('Exact passed source and truthful closed allocation required')
        if ('reference_alternatives' in proof
                and passed[0].get('named_endpoint_variant_controls') != row.get('named_endpoint_variant_controls')):
            raise ValueError('Named variant controls must come from the actual archived source row')
    return binding

def require_original_binding(contract, original, inventory):
    validate(contract)
    if contract.get('goal_revision'):
        if contract['goal_revision'].get('version') == 'native-local-coverage-same-capability-derived-v1':
            from .map_local_coverage_goal_revision import require_original_binding as require_goal_binding
        elif contract['goal_revision'].get('version') == 'explicit-missing-route-training-v1':
            from .map_missing_route_revision import require_original_binding as require_goal_binding
        else:
            from .map_route_goal_revision_binding import require_original_binding as require_goal_binding
        return require_goal_binding(contract, original, inventory)
    if contract.get('training_initialization'):
        from .map_route_initialization_binding import require_original_binding as require_training_binding
        return require_training_binding(contract, original, inventory)
    if {k:v for k,v in contract.items() if k != 'admission_result'} != original:
        raise ValueError('Original route definition changed after controls')
    def path(url):
        u = urlsplit(url)
        return u.path+('?' + u.query if u.query else '')+('#' + u.fragment if u.fragment else '')
    starts = [path(u) for u in inventory.get('recorded_start_urls', [])]
    if (inventory.get('task_id') != contract['source_task_id']
            or inventory.get('domain') != 'map'
            or inventory.get('heldout_quarantine') is not False
            or inventory.get('goal') != contract['goal']
            or inventory.get('source_trace_ids') != contract['source_trace_ids']
            or not starts or contract['start_path'] != starts[0]):
        raise ValueError('Authoritative source goal, split, traces or first start changed')

def fields(contract):
    validate(contract)
    kind = contract['completion_kind']
    return {'distance':['distance'], 'duration':['duration'],
            'distance_and_duration':['distance','duration'], 'mode_times':['times'],
            'ordered_streets':['streets'], 'longest_turn_segments':['turn_numbers']}.get(kind, [])

def public_goal(contract):
    names = fields(contract)
    if not names:
        return contract['goal']
    definitions = {
        'distance':'distance: {"value": a number, "unit": "m" or "km"}',
        'duration':'duration: {"hours": an integer, "minutes": an integer}',
        'times':'times: an object keyed by each requested mode ('+', '.join(contract['allowed_modes'])+'), with {"hours": an integer, "minutes": an integer} per mode',
        'streets':'streets: the complete ordered array of street names',
        'turn_numbers':'turn_numbers: an ascending array of all turn numbers tied for the largest distance displayed in the turn-by-turn list; compare displayed m and km in common units',
    }
    return contract['goal']+'\nResponse format: finish with a JSON answer containing exactly '+', '.join(names)+'. '+ '; '.join(definitions[n] for n in names)+'.'

def feedback(judgment):
    return routes.feedback(judgment)

class NativeRouteReadHooks:
    def __init__(self, contract, proof, directory):
        require_admission(contract, proof)
        self.core = routes.NativeNormalRouteHooks(contract, proof, Path(directory)/'native-route')
        self.context = None
        self.trace_provided = False
        self.final_answer = None
        self.scored = False

    def prepare(self, site, username):
        if username is not None:
            raise ValueError('Anonymous native Map routes must not borrow another website login')
        self.core.prepare(site)

    def attach(self, context):
        self.core.attach_context(context, self.core.site.url)
        self.context = context

    def observe_initial(self, page):
        if self.context is None or page.context is not self.context:
            raise ValueError('Actual normal first page must belong to the attached native context')
        self.core.page = page
        self.core.observe_initial(page)

    def record(self, page, *, event='observation'):
        return self.core.record(page, event=event)

    def capture_terminal(self, page, terminal):
        self.core.terminal(page, terminal)

    def provide_trace(self, trace):
        if not isinstance(trace, dict) or self.scored or self.trace_provided:
            raise ValueError('One actual completed rollout must precede terminal scoring')
        from .admin_pilot import final_answer
        text = final_answer(trace)
        try:
            self.final_answer = json.loads(text)
        except (ValueError, TypeError):
            self.final_answer = None
        self.trace_provided = True

    def score_terminal(self, site, terminal, *, runtime_error=None):
        if site is not self.core.site or self.scored or not self.trace_provided:
            raise ValueError('One terminal judgment must follow the actual source rollout')
        self.scored = True
        integrity = False
        try:
            site.reset_guard.require_unchanged()
            integrity = site.fingerprint() == self.core.proof['full_native_baseline']
            judgment = self.core.evaluate(site, terminal, answer=self.final_answer,
                                          runtime_error=runtime_error) if integrity else None
        except Exception as error:
            from .runtime_diagnostics import failure_diagnostic
            self.core.save('normal-route-protection-error', failure_diagnostic(error, 'native_route_terminal_protection'))
            judgment = None
        if judgment is None:
            judgment = {'version':routes.VERSION, 'status':'unknown', 'reward':None,
                        'checks':{'complete_native_protection_certified':integrity},
                        'reason':'Full native route protection or reference unavailable'}
        return judgment, integrity

    def close(self):
        self.core.close()

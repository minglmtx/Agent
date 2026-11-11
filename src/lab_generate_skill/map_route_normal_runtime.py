"""Staged normal BrowserGym hooks for source-bound native route completion.

This is a common runtime primitive, not an actor strategy. All references stay
private and must be independently built from the full native snapshot. Actual
source gates require two independent normal cold controls; a route capability
probe, a published success label, or a partial lifecycle cannot grant admission.
"""
from copy import deepcopy
import hashlib,json,math,re
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from .map_route_archive_semantics_v2 import require_derived_evidence, VERSION as ARCHIVE_SEMANTICS_VERSION
from .map_route_normal_capture import NativeRouteCapture,complete_route,exact_pair,fingerprint,terminal_checks
from .map_route_reference_variants import (entries as reference_entries, matching_reference,
    validate_variants, require_variant_controls)

VERSION='map-source-native-route-normal-v1'
LIFECYCLE=('protected_state_unchanged','clean_reset_verified','dirty_reuse_refused','cold_teardown_completed')
CONTROL_NAMES=('actual_normal_make_session','normal_noop_rejected','actual_correct_terminal_passed',
    'wrong_endpoint_or_invalid_open_choice_rejected','wrong_mode_or_explicit_mode_inapplicable',
    'unsubmitted_change_rejected','wrong_document_rejected','404_rejected','login_rejected')


def source_binding(contract):
    keys=('source_task_id','original_binding_sha256','goal','start_path','source_trace_ids',
          'endpoint_request','allowed_modes','completion_kind','initialization_revision','task_text_revision')
    if any(key not in contract for key in keys):raise ValueError('Full original or declared derivative route binding required')
    binding={key:deepcopy(contract[key])for key in keys}
    binding['optimization_scope']=deepcopy(contract.get('optimization_scope'))
    if contract['completion_kind']=='longest_turn_segments':
        # Invalidates older controls that used inaccessible backend precision.
        binding['turn_distance_metric']='native_displayed_row_metres_v1'
    if contract.get('training_initialization'):
        from .map_route_initialization_binding import validate as validate_initialization
        from .source_revision_binding import binding as source_revision_binding
        validate_initialization(contract)
        binding['training_initialization']=deepcopy(contract['training_initialization'])
        binding['source_revision_binding']=source_revision_binding(contract)
    if contract.get('goal_revision'):
        if contract['goal_revision'].get('version') == 'native-local-coverage-same-capability-derived-v1':
            from .map_local_coverage_goal_revision import validate as validate_goal_revision
        elif contract['goal_revision'].get('version') == 'explicit-missing-route-training-v1':
            from .map_missing_route_revision import validate as validate_goal_revision
        else:
            from .map_route_goal_revision_binding import validate as validate_goal_revision
        from .source_revision_binding import binding as source_revision_binding
        validate_goal_revision(contract)
        binding['task_id']=contract['task_id']
        binding['goal_revision']=deepcopy(contract['goal_revision'])
        binding['source_revision_binding']=source_revision_binding(contract)
    return binding


def reference_snapshot(proof):
    value={k:deepcopy(proof.get(k))for k in('references','native_field_scope','initial_rendered_route_spec','native_optimization_protocol')}
    for key in ('named_destination_identity','destination_identity_candidates'):
        if proof.get(key) is not None:value[key]=deepcopy(proof[key])
    if proof.get('open_choice_completion_protocol')is not None:
        value['open_choice_completion_protocol']=deepcopy(proof['open_choice_completion_protocol'])
    for key in ('reference_alternatives','named_endpoint_evidence','initial_native_reference'):
        if key in proof:value[key]=deepcopy(proof[key])
    return value


def reference_semantics(proof):
    """Only ephemeral HTTP receipt hashes differ across leased cold origins.

    Keep full actual receipt hashes in each independent snapshot; this separate
    signature retains exact backend body, endpoint/OSM identity, native visible
    reference, mode, source scope, field and optimization semantics. Never strip
    coordinates, task data, object IDs, rendered rows or source definitions.
    """
    value=reference_snapshot(proof)
    refs=list((value.get('references')or{}).values())
    if 'initial_native_reference' in value:refs.append(value['initial_native_reference'])
    refs.extend(ref for alternatives in (value.get('reference_alternatives')or{}).values() for ref in alternatives)
    from .map_route_reference_semantics import normalize_geocode_receipts
    for ref in refs:
        normalize_geocode_receipts(ref, value.get('named_endpoint_evidence') or {})
        receipt=ref.get('native_reference_receipt_sha256')
        if not re.fullmatch(r'[0-9a-f]{64}',str(receipt)):
            raise ValueError('Actual independent native transport receipt SHA required')
        if ref.get('native_goal_revision_version') is not None:
            from .map_route_goal_revision_binding import reference_semantics as goal_reference_semantics
            semantic=goal_reference_semantics(ref)
            ref.clear();ref.update(semantic)
        else:
            del ref['native_reference_receipt_sha256']
    for evidence in (value.get('named_endpoint_evidence')or{}).values():
        receipt=evidence.get('native_receipt_sha256')
        if not re.fullmatch(r'[0-9a-f]{64}',str(receipt)):
            raise ValueError('Complete native endpoint receipt SHA required')
        del evidence['native_receipt_sha256']
    if proof.get('named_destination_identity') is not None:
        from .map_destination_field_identity import semantics as named_semantics
        value['named_destination_full_semantics']=named_semantics(
            {'endpoint_request':{'query':proof['native_field_scope']['original_query']}},proof)
        value.pop('named_destination_identity',None)
        value.pop('destination_identity_candidates',None)
    return value


def require_source_gate(contract,proof,*,controls_only=False):
    from .original_reference_bytes import reference_sources
    with reference_sources(proof):
        return _require_source_gate(contract,proof,controls_only=controls_only)


def _require_source_gate(contract,proof,*,controls_only=False):
    binding=source_binding(contract)
    if proof.get('version')!=VERSION or proof.get('source_binding_sha256')!=fingerprint(binding):
        raise ValueError('Private native references must bind the entire original source definition')
    if not re.fullmatch(r'[0-9a-f]{64}',str(proof.get('full_native_baseline',''))):
        raise ValueError('Full native persistent snapshot fingerprint required')
    if contract.get('training_initialization'):
        from .map_route_initialization_binding import require_initial_reference
        require_initial_reference(contract,proof)
    refs=proof.get('references')
    if contract['endpoint_request']['kind']=='two_actor_chosen_distinct_points':
        from .map_open_route_choice import validate_contract,PROTOCOL
        validate_contract(contract)
        if proof.get('open_choice_completion_protocol')!=PROTOCOL:
            raise ValueError('Full source-bound original open-route completion boundary required')
    field_only=contract['completion_kind']=='native_destination_field'
    if not isinstance(refs,dict)or (not refs and not field_only):raise ValueError('Independent full native reference set required')
    if field_only:
        scope=proof.get('native_field_scope')
        if (not isinstance(scope,dict)or scope.get('version')!='native-route-destination-field-v1'
                or scope.get('input_name')!='route_to'or scope.get('original_query')!=contract['endpoint_request'].get('query')
                or scope.get('completion_boundary')!='destination_input_and_actual_native_location_not_route_completion'):
            raise ValueError('Explicit original destination-input boundary is required')
        if contract['endpoint_request'].get('query') is not None:
            from .map_destination_field_identity import require as require_named_destination
            require_named_destination(contract,proof)
    if contract.get('goal_revision', {}).get('version') == 'native-local-coverage-same-capability-derived-v1':
        from .map_local_coverage_goal_revision import require_native_evidence
        require_native_evidence(contract, proof)
    elif contract.get('goal_revision', {}).get('version') == 'explicit-missing-route-training-v1':
        from .map_missing_route_revision import require_native_evidence
        require_native_evidence(contract, proof)
    validate_variants(contract,proof)
    for profile,reference in reference_entries(proof):
        if profile not in contract['allowed_modes'] or profile not in ('car','bike','foot'):
            raise ValueError('Native reference belongs to an undeclared mode')
        if (reference.get('independent_native_read')is not True or not reference.get('native_reference_receipt_sha256')
                or reference.get('native_body_sha256')!=fingerprint(reference.get('native_body'))):
            raise ValueError('Independent native body provenance is incomplete')
        if not re.fullmatch(r'[0-9a-f]{64}',str(reference['native_reference_receipt_sha256'])):
            raise ValueError('Native reference receipt SHA is malformed')
        complete_route(reference['native_body'])
        if contract.get('goal_revision'):
            if contract['goal_revision'].get('version') == 'native-local-coverage-same-capability-derived-v1':
                from .map_local_coverage_goal_revision import require_reference as require_goal_reference
            elif contract['goal_revision'].get('version') == 'explicit-missing-route-training-v1':
                from .map_missing_route_revision import require_reference as require_goal_reference
            else:
                from .map_route_goal_revision_binding import require_reference as require_goal_reference
            require_goal_reference(contract,reference)
        if reference.get('profile')!=profile or not exact_pair(reference.get('pair'),reference.get('scope',{}).get('pinned_request_pair')):
            raise ValueError('Native pair or transport reference changed')
        if reference['scope'].get('allowed_modes')!=[profile]:
            raise ValueError('Per-mode route reference has ambiguous role')
        kind=contract['endpoint_request']['kind']
        if kind in ('replace_one_endpoint','reverse_named_initial_route'):
            initial=reference['scope'].get('initial_request_pair')
            declared_initial=(proof.get('initial_rendered_route_spec')or{}).get('pair')
            if not exact_pair(initial,declared_initial):
                raise ValueError('Transformation requires the verified initial rendered route')
            if kind=='replace_one_endpoint':
                from .native_route_metadata import retained_original_pair
                if not exact_pair(initial,retained_original_pair(contract)):
                    raise ValueError('Replacement initial route differs from the original first route')
            elif not exact_pair(reference['pair'],list(reversed(initial))):
                raise ValueError('Reversal target must reverse the independently pinned initial route')
    if controls_only:return binding
    cycles=proof.get('normal_source_cycles')
    if contract.get('local_coverage_initialization'):
        from .map_local_coverage_goal_revision import require_reverse_operation
        if not isinstance(cycles,list) or len(cycles)!=2:
            raise ValueError('Both actual reverse-operation normal cold proofs required')
        for actual_cycle in cycles:
            snapshot=actual_cycle.get('private_reference_snapshot')
            if not isinstance(snapshot,dict) or actual_cycle.get('native_reverse_operation_controls')!=snapshot.get('native_reverse_operation_controls'):
                raise ValueError('Actual per-cold original reverse control binding changed')
            require_reverse_operation(contract,snapshot)
    if not isinstance(cycles,list)or len(cycles)!=2:raise ValueError('Two independent normal source cold proofs required')
    reference_sha=fingerprint(reference_snapshot(proof));semantic_sha=fingerprint(reference_semantics(proof))
    factories=[]
    for cycle in cycles:
        if (cycle.get('source_task_id')!=contract['source_task_id'] or cycle.get('source_binding_sha256')!=fingerprint(binding)
                or cycle.get('normal_candidate_passed')is not True or cycle.get('actual_terminal_control_job_state')not in ('COMPLETED','FAILED')
                or cycle.get('actor_attempts')!=0 or cycle.get('api_calls')!=0
                or any(cycle.get(k)is not True for k in LIFECYCLE)
                or any(cycle.get('controls',{}).get(k)is not True for k in CONTROL_NAMES)
                or any(not re.fullmatch(r'[0-9a-f]{64}',str(cycle.get(k,'')))for k in('complete_actual_archive_sha256','complete_actual_members_sha256'))
                or cycle.get('baseline')!=proof['full_native_baseline']):
            raise ValueError('Partial, mismatched or failed source lifecycle cannot be admitted')
        if (contract['completion_kind']=='longest_turn_segments'
                and cycle.get('controls',{}).get('correct_route_wrong_turn_answer_rejected')is not True):
            raise ValueError('Both cold cycles must reject an incorrect answer on the correct displayed route')
        if contract['endpoint_request']['kind']=='two_actor_chosen_distinct_points':
            if any(cycle.get('controls',{}).get(k)is not True for k in('all_original_modes_successfully_checked','another_allowed_valid_pair_passed','same_point_choice_rejected')):
                raise ValueError('Both another valid free choice and invalid same-point controls are required')
        require_variant_controls(proof,cycle)
        if cycle.get('per_cycle_complete_reference_snapshot')is True:
            native=cycle.get('private_reference_snapshot')
            if(not isinstance(native,dict)or native.get('full_native_baseline')!=proof['full_native_baseline']
                    or cycle.get('private_reference_set_sha256')!=fingerprint(reference_snapshot(native))
                    or (require_derived_evidence(cycle,native,proof) if proof.get('route_reference_semantics_version')==ARCHIVE_SEMANTICS_VERSION else cycle.get('private_reference_semantics_sha256'))!=semantic_sha
                    or fingerprint(reference_semantics(native))!=semantic_sha
                    or not re.fullmatch(r'[0-9a-f]{64}',str(cycle.get('private_reference_artifact_file_sha256','')))):
                raise ValueError('Each complete archived cold reference must have unchanged full native semantics')
            require_source_gate(contract,native,controls_only=True)
        elif cycle.get('private_reference_set_sha256')!=reference_sha:
            raise ValueError('Full native private source reference changed')
        factories.append(cycle.get('fresh_factory_id'))
    if any(not isinstance(x,str)or len(x)!=64 for x in factories)or len(set(factories))!=2:
        raise ValueError('Cold source factories must be genuinely independent')
    return binding


def feedback(judgment):
    return {'status':judgment['status'],'reward':judgment['reward'],
        'checks':[{'name':name,'passed':passed}for name,passed in judgment.get('checks',{}).items()],
        'private_expected_values_provided':False,'action_sequence_provided':False}


class NativeNormalRouteHooks:
    """The normal runner passes this hook through setup/observe/terminal/close."""
    def __init__(self,contract,proof,directory,*,controls_only=False):
        self.contract=deepcopy(contract);self.proof=deepcopy(proof)
        self.binding=require_source_gate(contract,proof,controls_only=controls_only)
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=False)
        self.site=None;self.page=None;self.capture=None;self.initial=None;self.current=None;self.closed=False;self.public_observations=[]

    def save(self,name,value):
        from lab_generate_skill.io_utils import atomic_write_json
        atomic_write_json(self.directory/(name+'.json'),value)

    def prepare(self,site):
        if (self.site is not None or site.domain!='map' or site.with_geographic_baseline is not True
                or site.track_changes is not True or site.fingerprint()!=self.proof['full_native_baseline']):
            raise ValueError('Exactly the independent full native factory is required')
        site.reset_guard.require_unchanged();self.site=site
        self.save('normal-route-prepare',{'version':VERSION,'source_binding_sha256':fingerprint(self.binding),
            'baseline':self.proof['full_native_baseline'],'actor_strategy_changed':False,'private_reference_in_actor_input':False})

    def attach(self,page,site_origin):
        self.attach_context(page.context,site_origin)
        self.page=page

    def attach_context(self,context,site_origin):
        """Passive capture also supports the normal shared read-hook slot."""
        if self.site is None or self.capture is not None or site_origin!=self.site.url:
            raise ValueError('Prepare the source before its normal first navigation')
        if self.contract['endpoint_request']['kind']=='two_actor_chosen_distinct_points':
            from .map_open_route_capture import OpenChoiceRouteCapture
            self.capture=OpenChoiceRouteCapture(context,self.site.route_urls,self.directory/'actual-native-routes',self.site.search_url)
        else:self.capture=NativeRouteCapture(context,self.site.route_urls,self.directory/'actual-native-routes')

    def observe_initial(self,page):
        actual,declared=urlsplit(page.url),urlsplit(self.contract['start_path'])
        initial_spec=self.proof.get('initial_rendered_route_spec')
        initial_ref=self.proof.get('initial_native_reference')
        origin=urlsplit(self.site.url)
        self.save('normal-route-initial-document',{'actual_url':page.url,
            'declared_start':self.contract['start_path'],
            'independent_initial_reference_available':bool(initial_ref)})
        same_document=(actual.path,actual.query)==(declared.path,declared.query)
        if not same_document and initial_spec and initial_ref:
            from .map_route_native_display import native_url_pair
            # Native directions.js rewrites the URL to zoom-dependent decimal
            # precision. This is allowed only alongside the exact captured
            # request, complete independent response and rendered state below.
            same_document=(actual.path==declared.path and native_url_pair(
                page.url,initial_ref['profile'],initial_ref['pair']))
        if (actual.scheme,actual.netloc)!=(origin.scheme,origin.netloc) or not same_document:
            raise ValueError('Original or explicitly declared first start was changed')
        if initial_spec:
            # Wait only for the explicitly declared initial native request; no
            # action or later actor choice supplies this prerequisite.
            page.wait_for_function("() => !!document.querySelector('#sidebar_content tr.turn') || !!document.querySelector('#sidebar_content .search_results_error')",timeout=30000)
            from lab_generate_skill.browser_page_wait import READY,probe_args
            page.wait_for_function(READY,arg=probe_args('map'),timeout=8000,polling=100)
        self.initial=self.record(page,event='initial')
        if initial_spec:
            if initial_ref:
                from .map_route_native_display import verified_route_checks
                responses=[r for r in self.capture.responses if r.get('complete_native_response') is True]
                if not responses:
                    raise ValueError('Initial route lacks its complete actual native request')
                checks=verified_route_checks(initial_spec,responses[-1],initial_ref['native_body'],
                    self.initial,page.url,pinned_pair=initial_ref['pair'])
            else:
                from lab_generate_skill.map_route import route_checks
                checks=route_checks(initial_spec,self.initial,page.url)
            if not all(checks.values()):
                raise ValueError('Declared initial route and current form do not agree')
        self.save('normal-route-initial',{'public_state':self.initial,'actual_url':page.url,
            'original_binding_sha256':fingerprint(self.binding)})

    def record(self,page,*,event='observation'):
        from lab_generate_skill.map_route import read_route
        self.current=read_route(page)
        row={'event':event,'actual_url':page.url,'public_state':deepcopy(self.current)}
        self.public_observations.append(row)
        self.save('normal-route-public-observation-'+str(len(self.public_observations)-1),row)
        return deepcopy(self.current)

    def terminal(self,page,terminal):
        terminal['map_native_route']=self.record(page,event='terminal')
        terminal['map_native_route_url']=page.url
        self.save('normal-route-terminal',{'public_state':terminal['map_native_route'],
            'actual_url':page.url,'captured_actual_native_request_count':len(self.capture.responses)})

    def close(self):
        if self.closed:return
        if self.capture is not None:self.capture.close()
        self.closed=True

    def evaluate(self,site,terminal,*,answer=None,runtime_error=None):
        def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
        if runtime_error or self.initial is None or self.capture is None:
            return unknown('Normal reset or native response capture is incomplete')
        # A prior wrong route is ordinary exploration. Preserve its original
        # error in the capture, but evaluate the independently verified final
        # successful native response, not every previous attempted object.
        site.reset_guard.require_unchanged()
        if site.fingerprint()!=self.proof['full_native_baseline']:
            return unknown('Full native persistent route state changed')
        state=(terminal or {}).get('map_native_route')
        current_url=(terminal or {}).get('map_native_route_url')
        if not isinstance(state,dict)or not isinstance(current_url,str):
            return unknown('Actual normal terminal route observation is missing')
        health={'valid_terminal_document':type((terminal or {}).get('http_status'))is int
            and 200<=terminal['http_status']<300 and terminal.get('error_page')is False and terminal.get('login_page')is False}
        if self.contract['endpoint_request']['kind']=='two_actor_chosen_distinct_points':
            from .map_open_route_choice import OpenRouteChoiceEvaluator
            from .map_open_route_reference import NativeOpenChoiceReferenceProvider
            if not hasattr(self,'open_choice_evaluator'):
                provider=NativeOpenChoiceReferenceProvider(site,self.contract,self.proof,self.directory/'private-open-choice-reference',actual_geocodes=getattr(self.capture,'geocodes',[]))
                self.open_choice_evaluator=OpenRouteChoiceEvaluator(self.contract,reference_provider=provider.reference,field_provider=provider.fields)
            return self.open_choice_evaluator.evaluate(self.capture.responses,state,current_url,health)
        if self.contract['completion_kind']=='native_destination_field':
            value=state.get('destination');initial=self.initial.get('destination')
            checks=dict(health,visible_native_destination_input=state.get('route_form_visible')is True,
                native_destination_changed=isinstance(value,str)and bool(value.strip())and value!=initial)
            query=self.contract['endpoint_request'].get('query')
            if query is not None:
                checks['requested_destination_literal']=isinstance(value,str)and value.strip().casefold()==query.strip().casefold()
                try:
                    from .map_destination_field_identity import require as require_named_destination
                    require_named_destination(self.contract,self.proof)
                except (ValueError,OSError):
                    return unknown('Complete independently verified semantic destination identity unavailable')
                identities=self.proof.get('destination_identity_candidates')
                if not isinstance(identities,list)or not identities:
                    return unknown('Complete independently declared native destination identities are unavailable')
                for item in identities:
                    record=item.get('full_geocode_record')
                    if (item.get('requested_query')!=query or not isinstance(record,dict)or not record
                            or item.get('full_geocode_sha256')!=fingerprint(record)
                            or not re.fullmatch(r'[0-9a-f]{64}',str(item.get('native_reference_receipt_sha256','')))
                            or item.get('independent_native_identity_read')is not True):
                        return unknown('Independent native destination identity provenance is incomplete')
                checks['actual_native_requested_destination_exists']=True
            else:
                # An open custom-location choice must resolve to actual native
                # data; an arbitrary nonsense token is not an invented place.
                from .map_native_route_reference_inventory import full_http,require_native_origin
                from urllib.parse import urlencode
                import time
                if checks['native_destination_changed']:
                    try:
                        receipt=full_http(require_native_origin(site.search_url)+'/search?'+urlencode({'q':value,'format':'jsonv2','addressdetails':1,'limit':50}),
                            self.directory/'terminal-native-field-reference','source-custom-destination',time.monotonic()+30)
                        results=receipt.get('value')
                        checks['actual_native_custom_location_exists']=receipt['status']=='complete_native_response'and isinstance(results,list)and bool(results)
                    except Exception:return unknown('Complete independent native custom-location lookup unavailable')
                else:checks['actual_native_custom_location_exists']=False
            okay=bool(checks)and all(v is True for v in checks.values())
            return {'version':VERSION,'status':'success'if okay else'failure','reward':1.0 if okay else 0.0,'checks':checks}
        candidates=[]
        for served in self.capture.responses:
            if served.get('complete_native_response')is not True:continue
            reference=matching_reference(self.proof,served['profile'],served['pair'])
            if reference is None:continue
            try:
                checks=terminal_checks(reference['scope'],served,reference['native_body'],state,current_url)
                checks.update(health)
            except ValueError:
                continue
            candidates.append((served,reference,checks))
        if not candidates:
            # A rendered route can exist even when our passive collector
            # rejected its request (for example, native waypoint hints).
            # Missing evidence after a capture error is not an actor failure.
            # An unrelated/invalid final document still fails independently;
            # a fully verified later route above can still supersede an error.
            if (health['valid_terminal_document'] and state.get('route_visible') is True
                    and getattr(self.capture, 'first_error', None)):
                return unknown('Rendered terminal route lacks complete native evidence after a capture error')
            return {'version':VERSION,'status':'failure','reward':0.0,'checks':dict(health,actual_submitted_requested_native_route=False)}
        served,reference,checks=next((v for v in reversed(candidates)if all(v[2].values())),candidates[-1])
        kind=self.contract['completion_kind']
        if kind in ('distance','duration','distance_and_duration'):
            from .map_route_readout import visible_readout,distance_time_answer_checks
            fields={'distance':('distance',),'duration':('duration',),'distance_and_duration':('distance','duration')}[kind]
            try:
                readout=visible_readout(state,complete_route(reference['native_body']))
                checks.update({'answer_'+k:v for k,v in distance_time_answer_checks(answer,readout,fields).items()})
            except ValueError:
                checks['complete_current_displayed_route_readout']=False
        elif kind=='mode_times':
            from .map_route_native_display import verified_route_checks
            from .map_route_readout import native_duration
            times=answer.get('times')if isinstance(answer,dict)else None
            if set(self.proof['references'])!=set(self.contract['allowed_modes']):
                return unknown('Independent full references for all comparison modes are incomplete')
            checks['all_requested_modes_observed_with_matching_routes']=True
            checks['complete_typed_mode_time_comparison_answer']=isinstance(times,dict)and set(times)==set(self.contract['allowed_modes'])
            for profile in self.proof['references']:
                ref=matching_reference(self.proof,profile,reference['pair'])
                if ref is None:
                    return unknown('Comparison modes lack a common independently identified endpoint pair')
                seen=False
                for observation in self.public_observations:
                    try:
                        for actual in self.capture.responses:
                            if(actual.get('complete_native_response')is True and actual['profile']==profile
                                    and exact_pair(actual['pair'],ref['pair'])):
                                seen=seen or all(verified_route_checks(ref['scope']['rendered_route_spec'],actual,
                                    ref['native_body'],observation['public_state'],observation['actual_url'],
                                    pinned_pair=ref['pair']).values())
                    except ValueError:
                        # An intermediate loading or unrelated route observation
                        # is exploration, not an evaluator exception.
                        continue
                captured=any(r.get('complete_native_response')is True and r['profile']==profile and exact_pair(r['pair'],ref['pair'])and fingerprint(complete_route(r['body']))==fingerprint(complete_route(ref['native_body']))for r in self.capture.responses)
                checks['all_requested_modes_observed_with_matching_routes']&=seen and captured
                expected=native_duration(complete_route(ref['native_body'])['duration'])
                value=times.get(profile)if isinstance(times,dict)else None
                checks['complete_typed_mode_time_comparison_answer']&=(isinstance(value,dict)and set(value)=={'hours','minutes'}
                    and type(value.get('hours'))is int and type(value.get('minutes'))is int
                    and value['hours']==expected['hours']and value['minutes']==expected['minutes'])
        elif kind=='ordered_streets':
            names=[]
            for step in complete_route(reference['native_body'])['legs'][0]['steps']:
                name=step.get('name','')
                if not isinstance(name,str):return unknown('Native route street names are malformed')
                if name and (not names or names[-1]!=name):names.append(name)
            value=answer.get('streets')if isinstance(answer,dict)else None
            checks['complete_ordered_native_street_names']=bool(names)and value==names
        elif kind=='longest_turn_segments':
            from .map_route_readout import displayed_longest_turn_numbers
            alternatives=reference['scope']['rendered_route_spec']['alternatives']
            native=[r['native'] for r in alternatives if r['profile']==served['profile']]
            if len(native)!=1:return unknown('Independent native turn display is unavailable')
            try:
                expected=displayed_longest_turn_numbers(native[0]['rows'],complete_route(reference['native_body']))
            except (ValueError,KeyError,TypeError):
                return unknown('Complete independently rendered turn distances are unavailable')
            # terminal_checks above still requires the actual complete rows,
            # route body, endpoints and mode to match this private reference.
            value=answer.get('turn_numbers')if isinstance(answer,dict)else None
            checks['all_tied_longest_displayed_turn_segments']=value==expected and isinstance(value,list)and all(type(v)is int for v in value)
        elif kind in ('highways','major_highways','specific_turns_at_intersection','fixed_location_relative_to_route'):
            # These source scopes require independently pinned native way /
            # intersection / location identities. OSRM name/ref text alone is
            # insufficient to pretend that a major-highway or junction object
            # has been independently identified.
            semantic=reference.get('completion_semantics')
            if (not isinstance(semantic,dict)or semantic.get('kind')!=kind
                    or semantic.get('independent_native_identity_read')is not True
                    or not isinstance(semantic.get('complete_identity_record'),dict)or not semantic['complete_identity_record']
                    or semantic.get('complete_identity_record_sha256')!=fingerprint(semantic['complete_identity_record'])
                    or not re.fullmatch(r'[0-9a-f]{64}',str(semantic.get('native_reference_receipt_sha256','')))
                    or not isinstance(semantic.get('answer_key'),str)or not semantic['answer_key']or 'expected_answer'not in semantic
                    or semantic.get('native_body_sha256')!=reference['native_body_sha256']
                    or semantic.get('full_native_baseline')!=self.proof['full_native_baseline']):
                return unknown('Complete independent native '+kind+' identity/reference protocol is not bound yet')
            value=answer.get(semantic['answer_key'])if isinstance(answer,dict)else None
            checks['complete_original_'+kind+'_answer']=value==semantic['expected_answer']
        elif kind not in ('displayed_route','transformed_route','all_turns_displayed'):
            return unknown('Complete original '+kind+' predicate is not bound yet')
        if self.contract.get('optimization_scope') and not self.proof.get('native_optimization_protocol_declared'):
            return unknown('Requested optimization scope is not declared and verified')
        okay=bool(checks)and all(v is True for v in checks.values())
        return {'version':VERSION,'status':'success'if okay else'failure','reward':1.0 if okay else 0.0,'checks':checks}

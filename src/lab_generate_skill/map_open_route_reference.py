"""Separate normal rendered references for freely chosen native endpoints.

The original task permits actor-selected locations. Those public field values
are queried as inputs, not treated as a golden answer: full native records must
identify the exact submitted request points. The routing body and full rendered
turns are independently read. No action or reference enters actor observations.
"""
from copy import deepcopy
from pathlib import Path
import time
import traceback
from urllib.parse import urlencode
from .map_route_normal_capture import NativeRouteCapture, complete_route, fingerprint, point, exact_pair
from .map_open_route_choice import IndependentReferenceUnavailable
from .map_native_route_reference_inventory import full_http, require_native_origin


class NativeOpenChoiceReferenceProvider:
    def __init__(self, site, contract, proof, directory, *, actual_geocodes=None):
        self.site=site;self.contract=deepcopy(contract);self.proof=deepcopy(proof)
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=False)
        self.reference_cache={};self.field_cache={}
        if actual_geocodes is not None and not isinstance(actual_geocodes,list):
            raise ValueError('Complete actual native geocoder history must be a list')
        self.actual_geocodes=actual_geocodes if actual_geocodes is not None else []
        for ref in proof['references'].values():
            key=fingerprint({'pair':ref['pair'],'profile':ref['profile']})
            states=ref.get('scope',{}).get('rendered_route_spec',{}).get('alternatives',[])
            if len(states)==1:
                self.reference_cache[key]={**deepcopy(ref),'independent_normal_browser':True,
                                           'rendered_state':deepcopy(states[0]['native'])}

    def _require_baseline(self):
        self.site.reset_guard.require_unchanged()
        if self.site.fingerprint()!=self.proof['full_native_baseline']:
            raise IndependentReferenceUnavailable('Protected complete native factory changed')

    def reference(self, pair, mode):
        self._require_baseline();key=fingerprint({'pair':pair,'profile':mode})
        if key in self.reference_cache:return deepcopy(self.reference_cache[key])
        out=self.directory/('independent-route-'+key);out.mkdir()
        from lab_generate_skill.io_utils import atomic_write_json
        from lab_generate_skill.runtime_diagnostics import failure_diagnostic
        from lab_generate_skill.runtime_watchdog import deadline_scope
        session=None;capture=None;primary=None;ref=None
        try:
            with deadline_scope('open_choice_complete_private_reference',60,result_path=out/'result.json'):
                coordinates=';'.join(str(point(p)[1])+','+str(point(p)[0])for p in pair)
                native=full_http(self.site.route_urls[mode]+'/route/v1/driving/'+coordinates+'?overview=false&steps=true',out/'native-body','complete-independent-route',time.monotonic()+30)
                if native['status']!='complete_native_response':
                    raise ValueError('Independent complete native routing response unavailable')
                complete_route(native['value'])
                from run_site_navigation_once import make_session
                from lab_generate_skill.gobrowse_runtime import BrowserTask
                from lab_generate_skill.map_route import read_route,route_path
                plain={**deepcopy(self.contract),'domain':'map','task_id':self.contract['source_task_id'],
                       'completion':{}}
                # Initial observation still uses the declared original/derived
                # start; only this private reference context navigates afterward.
                task=BrowserTask(task_id=plain['task_id'],domain='map',goal=plain['goal'],start_url=self.site.url+plain['start_path'])
                session=make_session(self.site,plain,out/'normal-reference-browser',{})(None,task)
                session.reset(42)
                capture=NativeRouteCapture(session.env.page.context,self.site.route_urls,out/'actual-normal-native-response')
                session.step('goto('+repr(self.site.url+route_path(pair,mode))+')')
                end=time.monotonic()+25;settled=None
                while time.monotonic()<end:
                    state=read_route(session.env.page)
                    if state['loading']is False and state['route_visible']is True and state['rows']:
                        if settled is None:settled=time.monotonic()
                        if time.monotonic()-settled>=.4:break
                    else:settled=None
                    session.env.page.wait_for_timeout(50)
                else:raise ValueError('Independent normal native route did not settle')
                actual=[r for r in capture.responses if r.get('complete_native_response')is True
                        and r['profile']==mode and exact_pair(r['pair'],pair)]
                if not actual or fingerprint(actual[-1]['body'])!=fingerprint(native['value']):
                    raise ValueError('Separate normal renderer did not receive the complete independent native body')
                ref={'pair':deepcopy(pair),'profile':mode,'native_body':native['value'],
                     'native_body_sha256':fingerprint(native['value']),
                     'native_reference_receipt_sha256':fingerprint(native),
                     'independent_native_read':True,'independent_normal_browser':True,
                     'rendered_state':state,'full_native_baseline':self.proof['full_native_baseline'],
                     'original_source_binding_sha256':self.proof['source_binding_sha256']}
                atomic_write_json(out/'complete-reference.json',ref)
                self.reference_cache[key]=ref
        except Exception as error:
            primary=error
            atomic_write_json(out/'first-error.json',{
                'diagnostic':failure_diagnostic(error,'open_choice_private_reference'),
                'private_complete_exception_message':str(error),
                'private_complete_traceback':traceback.format_exc()})
        finally:
            cleanup=[]
            for name,obj in (('capture',capture),('normal_reference_browser',session)):
                if obj is not None:
                    try:obj.close()
                    except Exception as error:
                        cleanup.append({'diagnostic':failure_diagnostic(error,'open_choice_cleanup_'+name),
                                        'private_complete_exception_message':str(error),
                                        'private_complete_traceback':traceback.format_exc()})
            if cleanup:
                atomic_write_json(out/'cleanup-errors.json',cleanup)
                # Both closes are attempted. A failed reference cleanup remains
                # evaluator unknown, never an ordinary wrong endpoint choice.
                if primary is None:
                    primary=IndependentReferenceUnavailable('Independent reference browser cleanup failed')
                    atomic_write_json(out/'first-error.json',failure_diagnostic(primary,'open_choice_cleanup'))
        if primary is not None:
            self.reference_cache.pop(key,None)
            raise IndependentReferenceUnavailable(type(primary).__name__+': '+str(primary))from primary
        self._require_baseline()
        return deepcopy(ref)

    def fields(self, state, pair):
        self._require_baseline();out=[]
        from .map_route_native_display import native_numeric_point
        from lab_generate_skill.io_utils import atomic_write_json
        for value,p in zip((state.get('origin'),state.get('destination')),pair):
            if not isinstance(value,str)or not value.strip()or native_numeric_point(value,p):
                out.append(None);continue
            key=fingerprint({'field':value,'point':p})
            if key not in self.field_cache:
                try:
                    observed=[]
                    for capture in self.actual_geocodes:
                        if (capture.get('complete_native_geocoder_response')is not True
                                or capture.get('full_native_records_sha256')!=fingerprint(capture.get('full_native_records'))):
                            continue
                        for row in capture['full_native_records']:
                            if (row.get('display_name')==value and type(row.get('osm_id'))is int
                                    and row['osm_id']>0 and row.get('osm_type')in('node','way','relation')
                                    and point([row['lat'],row['lon']])==point(p)):
                                observed.append(row)
                    # A reverse-geocoded display name need not be searchable
                    # as a free-text phrase. Use all matching actual identities
                    # for an independent native lookup; never choose by rank.
                    if observed:
                        prefixes={'node':'N','way':'W','relation':'R'}
                        ids=sorted({prefixes[r['osm_type']]+str(r['osm_id'])for r in observed})
                        query='/lookup?'+urlencode({'osm_ids':','.join(ids),'format':'jsonv2','addressdetails':1,'namedetails':1,'extratags':1})
                    else:query='/search?'+urlencode({'q':value,'format':'jsonv2','addressdetails':1,'namedetails':1,'extratags':1,'limit':50})
                    receipt=full_http(require_native_origin(self.site.search_url)+query,
                                      self.directory/'native-field-identities',key,time.monotonic()+30)
                    if receipt['status']!='complete_native_response'or not isinstance(receipt['value'],list):
                        raise ValueError('Complete native selected public-field identities unavailable')
                    if observed:
                        actual={(r['osm_type'],r['osm_id'],tuple(point([r['lat'],r['lon']])),r['display_name'])for r in observed}
                        returned={(r.get('osm_type'),r.get('osm_id'),tuple(point([r['lat'],r['lon']])),r.get('display_name'))for r in receipt['value']}
                        if not actual<=returned:
                            raise ValueError('Independent native lookup did not reproduce the complete actual selected identities')
                    record={'actual_public_field_value':value,'independent_native_query_read':True,
                            'complete_native_query_receipt_sha256':fingerprint(receipt),
                            'full_native_records':receipt['value'],'full_native_records_sha256':fingerprint(receipt['value']),
                            'actual_passive_native_identity_candidates':deepcopy(observed),
                            'first_result_rank_used':False}
                    atomic_write_json(self.directory/('field-proof-'+key+'.json'),record);self.field_cache[key]=record
                except Exception as error:
                    raise IndependentReferenceUnavailable(type(error).__name__+': '+str(error))from error
            out.append(deepcopy(self.field_cache[key]))
        self._require_baseline()
        return out

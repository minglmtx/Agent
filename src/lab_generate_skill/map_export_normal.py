"""Original native export queries/state/artifacts; strict normal controls only.

No model, task navigation, geographic writes, or private target in actor inputs.
Current-view queries use the last actually visible native map at answer time.
Manual selection accepts either native pointer or form-change interaction.
"""
import copy
import hashlib
import json
from pathlib import Path
from decimal import Decimal
from urllib.parse import urlsplit

from . import map_frontier_capabilities as cap
from . import map_export_native_geometry as geometry
from . import map_osm_artifact as artifact

VERSION='map-export-native-normal-v1'
ADMISSION_VERSION=VERSION+'-two-fresh'
KINDS={'current_bounds','maximum_area','too_large_reason','zoom_enables_export','different_selection','osm_download','selected_export_bounds'}
FIELDS={'selected_export_bounds':{'west':'number','south':'number','east':'number','north':'number'},
 'current_bounds':{'west':'number','south':'number','east':'number','north':'number'},
 'maximum_area':{'maximum_area':'number','unit':'string'},
 'too_large_reason':{'area_square_degrees':'number','maximum_area_square_degrees':'number','too_large':'boolean','reason':'string'}}
REASONS=('selected_area_exceeds_direct_export_limit','selected_area_within_direct_export_limit')


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def required_controls(kind,derived=False):
    names=['initial_no_op','positive','wrong_value','404','login']if kind in FIELDS else['initial_no_op','positive','404','login']
    extras={'selected_export_bounds':['positive_after_selection_change','previous_selection_answer','unselected_view_rejected','uncommitted_input_rejected'],
      'current_bounds':['positive_after_zoom','previous_view_answer'],'maximum_area':['wrong_unit'],
      'too_large_reason':['positive_small_view','wrong_reason'],'zoom_enables_export':['positive_no_sidebar','insufficient_zoom'],
      'different_selection':['positive_coordinate_change','activated_unchanged','input_not_committed'],
      'osm_download':['positive_different_selected_area','wrong_selection_artifact','wrong_file','form_without_download']}
    names+=extras[kind]
    if derived:names+=['wrong_original_center']
    return names


def validate(contract):
    if contract.get('ordered_export') is not None:
        raise ValueError('Ordered export requires its own composition admission; plain download proof is insufficient')
    spec=contract.get('map_export')
    if contract.get('domain')!='map' or not isinstance(spec,dict) or spec.get('version')!=VERSION or spec.get('kind')not in KINDS:
        raise ValueError('Exact native Export normal contract required')
    if spec.get('view_referent')!='latest_actual_native_map_at_answer' or spec.get('unit')!='square_degrees':
        raise ValueError('Explicit public current-view/unit policy required')
    if contract.get('heldout_quarantine')is not False or type(contract.get('eligible_for_training'))is not bool:
        raise ValueError('Explicit local training eligibility policy required')
    if spec['kind']=='selected_export_bounds'and (spec.get('area_policy')!='actor_selected_native_rectangle'
      or spec.get('selection_referent')!='actual_current_active_native_export_rectangle'
      or contract.get('completion_revision',{}).get('derived_task')is not True):
        raise ValueError('Explicit current active rectangle training initialization/scope required')
    if spec['kind']=='osm_download'and spec.get('area_policy')not in('actor_selected','contains_original_initial_native_center'):
        raise ValueError('Explicit native artifact target policy required')
    initial_policy=spec.get('initial_document_policy','native_map')
    if initial_policy not in ('native_map','native_document'):
        raise ValueError('Explicit native initial-document policy required')
    if initial_policy=='native_document'and (spec['kind']!='osm_download' or spec.get('area_policy')!='actor_selected'):
        raise ValueError('A non-map start cannot supply an initial-map or center referent')
    if spec.get('area_policy')=='contains_original_initial_native_center'and not contract.get('completion_revision',{}).get('derived_task'):
        raise ValueError('A missing original area cannot be silently replaced')
    if spec.get('required_controls')!=required_controls(spec['kind'],spec.get('area_policy')=='contains_original_initial_native_center'):
        raise ValueError('Complete fixed normal-control scope required')
    return spec


def fingerprint(contract):
    validate(contract)
    return digest({k:contract.get(k)for k in('task_id','source_task_id','domain','goal','original_goal','start_path',
      'recorded_start_paths','source_trace_ids','heldout_quarantine','completion_revision','map_export','public_answer_protocol')})


def public_goal(contract):
    spec=validate(contract);kind=spec['kind'];goal=contract['goal']
    if kind not in FIELDS:
        revision=contract.get('completion_revision',{})
        if revision.get('derived_task') is True and revision.get('original_goal_unchanged') is True:
            declaration=revision.get('public_text')
            if not isinstance(declaration,str) or not declaration.strip():
                raise ValueError('An unchanged-goal Export derivative requires its explicit public scope')
            return goal+'\n'+declaration
        return goal
    fields=FIELDS[kind]
    text=goal+' Return a JSON object with exactly these fields: '+json.dumps(fields)+'. '
    if kind=='selected_export_bounds':text+='Select an actual rectangle through native Export and report its currently selected west/south/east/north longitude/latitude degrees. This explicit local training initialization does not assume that the original published start already had a selected rectangle and does not use viewport bounds as the selected area.'
    elif kind=='current_bounds':text+='Coordinates are longitude/latitude degrees for the native map view displayed when answering, including its current viewport after opening any sidebar.'
    elif kind=='maximum_area':text+='Express the native direct-export area limit in square degrees and use unit="square_degrees".'
    else:text+='Compare the current native selected/export-view rectangle with the native direct-export limit. Use reason as one of '+json.dumps(REASONS)+'. This reports the observed size condition, not every possible server failure.'
    return text


def read_snapshot(page, *, timeout=20000):
    """Read the native current view, retaining search/directions auto-pan.

    The already-observed local path determines native readiness; an initial
    route URL is never rewritten or converted to a home-page center target.
    """
    from .map_view import read_map_view, wait_native_view
    from .map_local_capabilities import wait_current_native_view
    view=read_map_view(page)
    if view.get('map_visible')is True:
        actual=urlsplit(page.url)
        if actual.path in ('/search','/directions'):
            local=actual.path+('?' + actual.query if actual.query else '')+('#' + actual.fragment if actual.fragment else '')
            view=wait_native_view(page,local,timeout=timeout)
        else:
            view=wait_current_native_view(page,timeout=timeout)
    size=page.evaluate("() => {const m=document.querySelector('#map');return m&&m.getClientRects().length?{width:m.clientWidth,height:m.clientHeight}:null}")
    return {'version':VERSION,'url':page.url,'view':view,'size':size,
      'panel':geometry.read_map_panel(page),'selection':geometry.selection_state(page)}


def current_bounds(snapshot):
    if not isinstance(snapshot,dict)or snapshot.get('version')!=VERSION:raise ValueError('Actual native snapshot required')
    view=snapshot['view'];size=snapshot['size'];cap.native_view(view)
    panel=snapshot['panel'];form=panel.get('export_form')
    if isinstance(form,dict)and form.get('visible')is True and form.get('selection_active')is not True:
        value=cap.form_bounds(panel)
        if not geometry.bounds_match_projection(value,view,size):raise ValueError('Native form/current viewport geometry differs')
        return value
    return cap.bounds(geometry.projected_bounds(view,size))


def export_area_bounds(snapshot):
    form=snapshot.get('panel',{}).get('export_form')
    if isinstance(form,dict)and form.get('visible')is True:
        values=cap.form_bounds(snapshot['panel'])
        if form.get('selection_active')is True and not geometry.selection_bounds_match(values,snapshot['view'],snapshot['selection']):
            raise ValueError('Actual selected area and native selection geometry differ')
        if form.get('selection_active')is not True and not geometry.bounds_match_projection(values,snapshot['view'],snapshot['size']):
            raise ValueError('Actual native Export view differs from form bounds')
        return values
    return current_bounds(snapshot)


def _answer(contract,answer):
    if isinstance(answer,str):
        try:answer=json.loads(answer)
        except ValueError:return None
    fields=FIELDS[contract['map_export']['kind']]
    if not isinstance(answer,dict)or set(answer)!=set(fields):return None
    for key,kind in fields.items():
        value=answer[key]
        if kind=='number':
            if type(value)not in(int,float):return None
            try:cap.decimal(value)
            except ValueError:return None
        elif kind=='boolean'and type(value)is not bool:return None
        elif kind=='string'and not isinstance(value,str):return None
    return answer


def _same_number(a,b,tolerance=Decimal('0.00000001')):
    return abs(cap.decimal(a)-cap.decimal(b))<=tolerance


def _health(page,origin):
    if not isinstance(page,dict)or any(k not in page for k in('url','http_status','login_page','error_page')):raise ValueError('Actual terminal page health missing')
    block = page.get('navigation_policy_block')
    if (page['url'] == 'chrome-error://chromewebdata/' and page['http_status'] is None
            and page['error_page'] is True and page['login_page'] is False
            and isinstance(block, dict) and block.get('document_url') == page['url']
            and isinstance(block.get('blocked_origin'), str)
            and block.get('source') == 'local_network_policy'
            and block.get('reason') == 'outside_declared_local_services'):
        blocked = urlsplit(block.get('blocked_origin', ''))
        local = urlsplit(origin)
        if blocked.scheme in ('http', 'https') and blocked.netloc and (blocked.scheme, blocked.netloc) != (local.scheme, local.netloc):
            return {'correct_site': False, 'page_valid': False}
    if type(page['http_status'])is not int or not isinstance(page['url'],str)or any(type(page[k])is not bool for k in('login_page','error_page')):raise ValueError('Malformed terminal health')
    if not 200<=page['http_status']<500:raise ValueError('Native transport failed')
    p,s=urlsplit(page['url']),urlsplit(origin)
    return {'correct_site':(p.scheme,p.netloc)==(s.scheme,s.netloc),'page_valid':200<=page['http_status']<300 and not page['login_page']and not page['error_page']}


def artifact_checks(download,selection,initial,spec,origin):
    base={'real_native_download':False,'download_matches_actual_selected_area':False,
      'complete_native_database_expansion':False,'valid_nonempty_osm':False,'original_area_policy':False}
    if download is None:return base
    if not isinstance(download,dict)or not isinstance(selection,dict):raise ValueError('Actual native artifact evidence missing')
    reference=download.get('private_native_reference');record=download.get('metadata');path=download.get('file')
    if not isinstance(reference,dict)or not isinstance(record,dict)or not isinstance(path,str):raise ValueError('Incomplete native download evidence')
    p=Path(path)
    if not p.is_file()or p.stat().st_size>artifact.MAX_BYTES:raise ValueError('Actual native download file unavailable')
    payload=p.read_bytes()
    if record.get('bytes')!=len(payload)or record.get('sha256')!=hashlib.sha256(payload).hexdigest():raise ValueError('Saved native download evidence changed')
    expected=artifact.form_bbox(selection['panel'])
    actual=artifact.artifact_checks(record,payload,reference,origin)
    base.update(real_native_download=actual['download_completed']and actual['native_attachment_response'],
      download_matches_actual_selected_area=actual['correct_native_bounds']and expected==artifact.bbox(reference['bounds']),
      complete_native_database_expansion=actual['native_geometry_matches']and actual['native_full_payload_matches']and reference.get('native_database_expansion_verified')is True,
      valid_nonempty_osm=actual['valid_nonempty_osm'],original_area_policy=True)
    if spec['area_policy']=='contains_original_initial_native_center':
        _,lat,lon=cap.native_view(initial['view']);w,s,e,n=map(Decimal,expected)
        base['original_area_policy']=w<=Decimal(str(lon))<=e and s<=Decimal(str(lat))<=n
    return base


def evaluate(contract,page,answer,initial,current,reference,*,site_origin,download=None,selection=None):
    spec=validate(contract);kind=spec['kind']
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    try:checks=_health(page,site_origin)
    except ValueError as e:return unknown(str(e))
    if not all(checks.values()):return {'version':VERSION,'status':'failure','reward':0.0,'checks':checks}
    try:
        maximum=cap.decimal(reference['maximum_area_square_degrees'])
        if reference.get('native_setting_verified')is not True or maximum<=0:raise ValueError('Independent native setting reference missing')
        if kind not in ('maximum_area','osm_download'):
            visible=current.get('view',{}).get('map_visible') if isinstance(current,dict) else None
            if type(visible)is not bool:raise ValueError('Native terminal map visibility unavailable')
            checks['native_map_visible']=visible
            if not visible:return {'version':VERSION,'status':'failure','reward':0.0,'checks':checks}
        if kind in FIELDS:
            parsed=_answer(contract,answer);checks['answer_schema']=parsed is not None
            if parsed is None:return {'version':VERSION,'status':'failure','reward':0.0,'checks':checks}
            if kind=='maximum_area':checks.update(native_area_limit=_same_number(parsed['maximum_area'],maximum),area_unit=parsed['unit']=='square_degrees')
            else:
                if kind=='selected_export_bounds':
                    form=current.get('panel',{}).get('export_form')
                    checks['actual_active_native_selection']=isinstance(form,dict)and form.get('selection_active')is True
                    if not checks['actual_active_native_selection']:return {'version':VERSION,'status':'failure','reward':0.0,'checks':checks}
                    values=cap.form_bounds(current['panel'])
                    checks['native_selection_geometry']=geometry.selection_bounds_match(values,current['view'],current['selection'])
                    if not checks['native_selection_geometry']:return {'version':VERSION,'status':'failure','reward':0.0,'checks':checks}
                values=current_bounds(current)if kind=='current_bounds'else export_area_bounds(current);zoom=cap.native_view(current['view'])[0]
                tolerance=Decimal(1).scaleb(-geometry._precision(zoom))/2+Decimal('0.000000001')
                if kind in ('current_bounds','selected_export_bounds'):checks['current_native_bounds'if kind=='current_bounds'else'current_selected_export_bounds']=all(_same_number(parsed[k],v,tolerance)for k,v in zip(('west','south','east','north'),values))
                else:
                    size=cap.area(values);large=size>maximum
                    checks.update(native_area=_same_number(parsed['area_square_degrees'],size,Decimal('0.00001')),
                        native_area_limit=_same_number(parsed['maximum_area_square_degrees'],maximum),native_size_relation=parsed['too_large']is large,
                        causal_size_reason=parsed['reason']==REASONS[0 if large else 1])
        elif kind=='zoom_enables_export':
            values=current_bounds(current);checks.update(actual_native_zoom_in=cap.relative_zoom(initial['view'],current['view']),native_direct_export_size=cap.area(values)<maximum)
            form=current.get('panel',{}).get('export_form')
            if isinstance(form,dict):checks['native_form_eligible']=all(cap.export_checks(current['panel'],maximum,require_direct=True).values())
        elif kind=='different_selection':
            baseline=reference.get('first_export_bounds')
            if baseline is None:raise ValueError('Observed original default Export selection missing')
            checks.update(actual_different_selection=False,native_selection_geometry=False)
            if isinstance(current.get('panel',{}).get('export_form'),dict):
                try:values=cap.form_bounds(current['panel'])
                except ValueError:values=None
                if values is not None:
                    checks.update(actual_different_selection=tuple(map(Decimal,values))!=tuple(map(Decimal,cap.bounds(baseline))),
                      native_selection_geometry=geometry.selection_bounds_match(values,current['view'],current['selection']))
        else:checks.update(artifact_checks(download,selection,initial,spec,site_origin))
    except (KeyError,TypeError,ValueError)as e:return unknown(str(e))
    success=all(checks.values())
    return {'version':VERSION,'status':'success'if success else'failure','reward':float(success),'checks':checks}


def private_answer(contract,current,reference):
    kind=validate(contract)['kind'];maximum=cap.decimal(reference['maximum_area_square_degrees'])
    if kind=='maximum_area':return {'maximum_area':float(maximum),'unit':'square_degrees'}
    values=current_bounds(current)if kind=='current_bounds'else export_area_bounds(current)
    if kind in('current_bounds','selected_export_bounds'):return {k:float(v)for k,v in zip(('west','south','east','north'),values)}
    size=cap.area(values);large=size>maximum
    return {'area_square_degrees':float(size),'maximum_area_square_degrees':float(maximum),'too_large':large,'reason':REASONS[0 if large else 1]}


def feedback(judgment):
    meanings={'answer_schema':'The answer does not follow the public result schema.',
      'current_native_bounds':'The coordinates do not match the actual current native map view.',
      'area_unit':'The maximum area is not expressed in square degrees.',
      'native_area_limit':'The answer differs from the native direct-export limit.',
      'causal_size_reason':'The stated size cause does not match the observed area/limit relation.',
      'native_size_relation':'The reported too-large condition differs from the observed rectangle.',
      'native_selection_geometry':'The form coordinates and visible native selection do not agree.',
      'actual_different_selection':'The actual selected region is unchanged.',
      'download_matches_actual_selected_area':'The native artifact is for a different region than the actual selected area.'}
    return {'status':judgment['status'],'failures':[meanings.get(k,'A required observable completion condition is not satisfied.')for k,v in judgment.get('checks',{}).items()if v is False],
      'private_reference_values_provided':False,'action_sequence_provided':False}


def require_admission(contract,proof):
    validate(contract)
    if proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(contract)or proof.get('passed')is not True:raise ValueError('Normal task proof required; capability is insufficient')
    cycles=proof.get('cycles')
    if not isinstance(cycles,list)or len(cycles)!=2 or cycles[0].get('initial_fingerprint')!=cycles[1].get('initial_fingerprint')or not cycles[0].get('initial_fingerprint'):raise ValueError('Two equal fresh native baselines required')
    if any(not isinstance(x.get('fresh_instance_id'),str)or not x['fresh_instance_id']for x in cycles)or len({x.get('fresh_instance_id')for x in cycles})!=2:raise ValueError('Independent actual fresh instances required')
    expected=set(contract['map_export']['required_controls'])
    for cycle in cycles:
        if any(cycle.get(k)is not True for k in('protected_state_unchanged','clean_reset_verified','dirty_reuse_refused'))or cycle.get('initial_fingerprint')!=cycle.get('final_fingerprint'):raise ValueError('Native state protection/reset proof missing')
        rows=[r for r in cycle.get('tasks',[])if r.get('task_id')==contract['task_id']]
        if len(rows)!=1 or rows[0].get('passed')is not True or rows[0].get('original_start_verified')is not True or rows[0].get('reference_verified')is not True:raise ValueError('Original-start normal task controls missing')
        if rows[0].get('original_first_start')!=contract['start_path']or rows[0].get('normal_control_version')!=ADMISSION_VERSION or rows[0].get('reference',{}).get('native_setting_verified')is not True:
            raise ValueError('Bound original referent/native setting proof missing')
        verdicts=rows[0].get('checks',{})
        if set(verdicts)!=expected or any(verdicts[k]!='success'if k.startswith('positive')else verdicts[k]!='failure'for k in expected):raise ValueError('Full positive/negative task verdicts required')
    return True

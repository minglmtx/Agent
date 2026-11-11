"""Typed native Map information and local share artifacts, never LLM judging.

The original goal remains intact. An explicit local answer protocol defines
finite fields, not an actor plan or hidden answer. Share means returning a
verified native URL to the user; no external delivery or clipboard is claimed.
"""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

from .admin_query_rules import parse_answer
from .browser_prompt_contract import query_finish_instruction
from .map_local_capabilities import DOCUMENTS,document_content,digest,geo_triplet,same_center,map_triplet
from .map_metadata_query import native_geo_uri,initial_view,verify_sources
from .map_share_layout import resized_center
from .map_share_query import short_path
from .map_view import read_map_view
from .site_navigation_rules import valid_initial_page
from .site_query_rules import evaluate_query,reference_fingerprint,query_feedback

VERSION='map-typed-native-information-share-v1'
ADMISSION_VERSION='map-typed-native-information-share-admission-v1'
SHARE_RESULT_REVISION='original-view-answer-v2'
FIELDS={
 'license_terms':{'data_license':'string_choice','permissions':'record_set','attribution':'string_choice','derivative_condition':'string_choice'},
 'data_sources':{'overview':'string','sources':'record_subset'},
 'contributor_groups':{'groups':'record_set'},
 'share_link':{'share_link':'local_url'},
}
PATHS={'license_terms':'/copyright','data_sources':'/copyright','contributor_groups':'/about'}
RECORD_FIELDS={'license_terms':{'permissions':{'name':'string'}},
 'data_sources':{'sources':{'country':'string','description':'string'}},
 'contributor_groups':{'groups':{'description':'string'}}}


def normalized(text):return ' '.join(text.split())


def exactly(text,pattern):
    rows=re.findall(pattern,text,re.S)
    if len(rows)!=1:raise ValueError('Native information anchor missing or ambiguous')
    return rows[0]


def document_values(kind,body):
    """Extract actual native text; no model-invented summaries or source rows."""
    content=document_content(body,PATHS[kind]);text=normalized(content)
    if kind=='license_terms':
        label=exactly(text,r'OpenStreetMap® is open data, licensed under the (.*?) by the OpenStreetMap Foundation \(OSMF\)\.')
        if label!='Open Data Commons Open Database License (ODbL)':raise ValueError('Native data license identity changed')
        verbs,attribution,derivative=exactly(text,r'You are free to (.*?) our data, as long as (.*?)\. If you alter or build upon our data, (.*?)\.')
        terms=[s.strip()for s in re.split(r', | and ',verbs)]
        if not terms or len(set(terms))!=len(terms):raise ValueError('Native permission list malformed')
        return {'data_license':[label,'ODbL','Open Database License','Open Data Commons Open Database License'],
          'permissions':[{'name':s}for s in terms],
          'attribution':[attribution,attribution.removeprefix('you ')],
          'derivative_condition':[derivative,derivative.removeprefix('you ')]}
    if kind=='contributor_groups':
        group=exactly(text,r'Our contributors include (.*?), and many more\.')
        rows=[{'description':s.strip()}for s in group.split(', ')]
        if len(rows)<2 or any(not r['description']for r in rows):raise ValueError('Native named group list unavailable')
        return {'groups':rows}
    start='Our contributors are thousands of individuals. We also include openly-licensed data from national mapping agencies and other sources, among them:'
    if text.count(start)!=1:raise ValueError('Native source overview missing or ambiguous')
    lines=[normalized(line)for line in content.splitlines()if normalized(line)]
    a=lines.index('Our contributors')+1
    end=next(i for i in range(a,len(lines))if lines[i].startswith('For further details of these,'))
    records=[]
    for line in lines[a:end]:
        match=re.fullmatch(r'([^:]+): (.+)',line)
        if match:records.append({'country':match[1],'description':match[2]})
    if not records or len({r['country']for r in records})!=len(records):raise ValueError('Native source example records malformed')
    return {'overview':start,'sources':records}


def validate(contract):
    q=contract.get('map_typed')
    if (contract.get('domain')!='map' or not isinstance(q,dict) or q.get('version')!=VERSION or
        q.get('kind')not in FIELDS or q.get('fields')!=FIELDS[q['kind']]):
        raise ValueError('Explicit typed native Map protocol required')
    kind=q['kind']
    if kind in RECORD_FIELDS and q.get('record_fields')!=RECORD_FIELDS[kind]:raise ValueError('Typed native record fields changed')
    if kind=='data_sources' and q.get('minimum_records')!={'sources':1}:raise ValueError('Source examples require explicit nonempty scope')
    if kind=='share_link':
        if q.get('completion_interpretation')!='return_local_native_link_to_user_no_delivery_or_clipboard':
            raise ValueError('Explicit local-link completion interpretation required')
        if contract['start_path']!=q.get('reference_path'):raise ValueError('Share reference must preserve first original task start')
        parsed=urlsplit(q['reference_path'])
        if parsed.path!='/'or parsed.query or set(parse_qs(parsed.fragment))!={'map'}:raise ValueError('Original unmarked standard map required')
        center=resized_center(*initial_view(q['reference_path']),q.get('share_geometry',{}))
        short_path(*center)
        if q.get('original_layer_code')!='M':raise ValueError('This protocol requires the original native Standard layer')
    refs=q.get('reference_evidence',[])
    if (not isinstance(refs,list)or len(refs)!=2 or any(not isinstance(r,dict)or set(r)!={'file','sha256'}or
        not isinstance(r['file'],str)or not isinstance(r['sha256'],str)or not re.fullmatch('[0-9a-f]{64}',r['sha256'])for r in refs)or
        len({str(Path(r['file']).resolve())for r in refs})!=2):
        raise ValueError('Two independently pinned full native references required')
    return q


def reference(contract,site=None):
    q=validate(contract);kind=q['kind'];documents=[]
    if site is not None:verify_sources(site,q)
    for r in q['reference_evidence']:
        path=Path(r['file']);raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('Native reference evidence changed')
        row=json.loads(raw)
        if kind=='share_link':
            if (row.get('source_task_id')!=contract['source_task_id']or row.get('start_path')!=contract['start_path']or
                row.get('goal')!=contract['goal']or row.get('passed')is not True):raise ValueError('Share reference not this original source')
            if row.get('independent_share_geometry')!=q['share_geometry']:raise ValueError('Independent native share layouts differ')
            expected=resized_center(*initial_view(contract['start_path']),q['share_geometry'])
            if not same_center(expected,tuple(row['independent_expected_center'])):raise ValueError('Native Share projection differs')
            native=row['controls']['positive']['pages'][0]['share']
            origin=urlsplit(native['long_href']);site_origin=origin.scheme+'://'+origin.netloc
            if not share_payload_checks(contract,native,site_origin):raise ValueError('Native reference payload/layer mismatch')
        else:
            if row.get('http_status')!=200 or row.get('requested_path')!=PATHS[kind]:raise ValueError('Wrong independent native document')
            documents.append(document_values(kind,row['body']))
    if kind=='share_link':
        center=resized_center(*initial_view(contract['start_path']),q['share_geometry'])
        value={'object_id':'map-native-share:'+reference_fingerprint({'start':contract['start_path'],'geometry':q['share_geometry']}),
          'values':{'share_link':{'short_path':short_path(*center),'center':list(center),'layer_code':'M'}}}
    else:
        if documents[0]!=documents[1]:raise ValueError('Independent native answer references differ')
        value={'object_id':'map-native-information:'+kind,'values':documents[0]}
    return value


def public_goal(contract):
    q=validate(contract)
    description=q['field_meanings']
    instructions=query_finish_instruction(q['fields'])+' Return only the requested JSON fields inside answer. Field meanings: '+json.dumps(description)+'.'
    for name,shape in q.get('record_fields',{}).items():
        instructions+=' '+name+' must be a JSON array with exactly these record fields: '+json.dumps(shape)+'.'
        instructions+=' Include every explicitly named example.'if q['fields'][name]=='record_set'else' Return at least one correct complete source example; more are allowed.'
    if q['kind']=='share_link':instructions+=' Return a complete native long or short URL on the current task website. This protocol checks returning a usable link; it does not require sending to an external recipient or copying to a clipboard.'
    return contract['goal']+'\n'+instructions


def query_projection(contract):
    q=validate(contract)
    return {**contract,'query':{k:v for k,v in q.items()if k in ('fields','record_fields','minimum_records')}}


def fingerprint(contract):
    content={k:contract.get(k)for k in ('task_id','source_task_id','domain','goal','start_path','recorded_start_paths','map_typed','heldout_quarantine','completion_revision','environment_revision')}
    if contract.get('map_typed',{}).get('kind')=='share_link':
        content['share_result_revision']=SHARE_RESULT_REVISION
    return reference_fingerprint(content)


def layer_code(url):
    p=urlsplit(url);values=parse_qs(p.fragment if p.path=='/'else p.query,keep_blank_values=True)
    if any(k not in ('map','layers')for k in values) or any(len(v)!=1 for v in values.values()):raise ValueError('Unexpected native link payload')
    layers=values.get('layers',['M'])[0]
    if not layers or layers=='M':return'M'
    return layers


def local_url(value,origin):
    if not isinstance(value,str):return False
    p=urlsplit(value);base=urlsplit(origin)
    return p.scheme in ('http','https')and (p.scheme,p.netloc)==(base.scheme,base.netloc)and not p.username and not p.password


def share_url_matches(contract,value,site_origin):
    if not local_url(value,site_origin):return False
    q=contract['map_typed'];p=urlsplit(value)
    try:
        if layer_code(value)!=q['original_layer_code']:return False
        expected=resized_center(*initial_view(contract['start_path']),q['share_geometry'])
        if p.path.startswith('/go/'):
            return not p.fragment and p.path==short_path(*expected)and not p.query
        return p.path=='/'and not p.query and same_center(expected,map_triplet(value))
    except (TypeError,ValueError,KeyError):return False


def share_payload_checks(contract,state,site_origin):
    if not isinstance(state,dict)or state.get('visible')is not True:return False
    if not all(share_url_matches(contract,state.get(k),site_origin)for k in ('long_href','short_href')):return False
    for kind in ('long','short'):
        if state.get(kind+'_visible')is True:
            if state.get(kind+'_value')!=state.get(kind+'_href'):return False
    return any(state.get(k+'_visible')is True for k in ('long','short'))


def result_url_matches(contract,value,site_origin):
    """The native sidebar may pan; that cannot redefine the requested result.

    Keep the calibrated Share-artifact check above separate from the answer.
    The public task asks for the initial view and layer, not the resized view.
    """
    from .map_initial_view_link import local_link
    return local_link(value,site_origin,initial_view(contract['start_path']))


SHARE_READ=r'''() => {
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const ui=document.querySelector('.share-ui');
 const state={visible:visible(ui),map_visible:visible(document.querySelector('#map')),
   base_control_count:document.querySelectorAll('.base-layers input[type=radio]').length,
   overlay_control_count:document.querySelectorAll('.overlay-layers input[type=checkbox]').length,
   active_base_labels:[...document.querySelectorAll('.base-layers li.active label')].map(e=>e.textContent.trim()),
   checked_base_labels:[...document.querySelectorAll('.base-layers label')].filter(e=>e.querySelector('input')?.checked).map(e=>e.textContent.trim()),
   active_overlay_labels:[...document.querySelectorAll('.overlay-layers label')].filter(e=>e.querySelector('input')?.checked).map(e=>e.textContent.trim())};
 if(!state.visible)return state;
 for(const kind of ['long','short']){
   const input=ui.querySelector('#'+kind+'_input');
   state[kind+'_visible']=visible(input);
   state[kind+'_value']=state[kind+'_visible']?input.value:null;
   state[kind+'_href']=ui.querySelector('#'+kind+'_link')?.getAttribute('href')||null;
 }
 return state;
}'''


def read_share_state(page):
    """Read only native visible artifact state; no tab clicks or clipboard access."""
    # The scorer receives separately captured terminal health. Do not retain
    # arbitrary document/iframe URL hashes in an artifact observation.
    return page.evaluate(SHARE_READ)


def evaluate(contract,page,answer,initial,final,*,site_origin,observations=None,runtime_error=None):
    q=validate(contract)
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    if q['kind']!='share_link':
        if initial!=reference(contract):return unknown('Native task reference does not match pinned independent documents')
        return evaluate_query(query_projection(contract),page,answer,initial,final,site_origin=site_origin,runtime_error=runtime_error)
    if initial!=final or initial!=reference(contract):return unknown('Native initial-view reference missing or changed')
    if not isinstance(observations,list):return unknown('Native Share observation history missing')
    if (not isinstance(page,dict)or type(page.get('http_status'))is not int or not isinstance(page.get('url'),str)or
        any(type(page.get(k))is not bool for k in ('login_page','error_page'))or not 200<=page['http_status']<500):return unknown('Missing final document or transport/server error')
    try:
        value=parse_answer(answer);schema=set(value)=={'share_link'}
    except (ValueError,TypeError):value={};schema=False
    seen=[state for state in observations if share_payload_checks(contract,state,site_origin)]
    artifact=any(state.get('map_visible')is True and type(state.get('base_control_count'))is int and state['base_control_count']>0 and
        type(state.get('overlay_control_count'))is int and state['overlay_control_count']>0 and
        state.get('active_base_labels')==state.get('checked_base_labels')==['Standard']and state.get('active_overlay_labels')==[]for state in seen)
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),'answer_schema':schema,
       'native_share_artifact_observed':artifact,'requested_view_and_layer_returned':result_url_matches(contract,value.get('share_link'),site_origin),
       'source_reference_unchanged':initial==final}
    success=all(checks.values())
    return {'version':VERSION,'scoring_revision':SHARE_RESULT_REVISION,
            'status':'success'if success else'failure','reward':float(success),'checks':checks,'reason':None}


def feedback(j):
    base=query_feedback(j)
    meanings={'native_share_artifact_observed':'A native Share panel artifact for the initial task view and layer was observed.',
       'requested_view_and_layer_returned':'The returned local URL represents the initial task view and layer.',
       'source_reference_unchanged':'The original native task reference remains unchanged.'}
    for row in base['checks']:
        if row['name']in meanings:row['condition']=meanings[row['name']]
    return base


def expected_controls(contract,values):
    q=validate(contract)
    if q['kind']=='share_link':
        return {name:('success'if name in ('positive','long_link','closed_panel_retention','restored_positive')else'failure')for name in
          ('positive','long_link','closed_panel_retention','restored_positive','initial_no_op','panel_only','answer_without_artifact',
           'wrong_native_view','wrong_native_layer','tampered_native_input','sidebar_shifted_answer','wrong_layer_answer','foreign_url','404','login')}
    from .query_record_sets import negative_record_answers,positive_record_answers
    return {'positive':'success','answer_retention':'success','restored_positive':'success',
       'initial_no_op':'failure','wrong_value':'failure','wrong_native_object':'failure','404':'failure','login':'failure',
       **{k:'failure'for k in negative_record_answers(query_projection(contract)['query'],values)},
       **{k:'success'for k in positive_record_answers(query_projection(contract)['query'],values)}}


def require_admission(contract,proof):
    """Require full ordinary two-fresh controls, not capability or page opening."""
    if contract.get('heldout_quarantine'):raise ValueError('Heldout Map source cannot enter development')
    ref=reference(contract)
    if (proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(contract)or
        proof.get('passed')is not True):raise ValueError('Typed Map normal proof is stale, mismatched or failed')
    cycles=proof.get('cycles')
    if not isinstance(cycles,list)or len(cycles)!=2 or [c.get('cycle')for c in cycles]!=[0,1]:
        raise ValueError('Two independent fresh typed Map cycles required')
    baselines=[]
    for cycle in cycles:
        if (not cycle.get('initial_fingerprint')or cycle.get('initial_fingerprint')!=cycle.get('final_fingerprint')or
            cycle.get('clean_reset_verified')is not True or cycle.get('dirty_reuse_refused')is not True):
            raise ValueError('Full native protected state and clean/dirty reset controls required')
        baselines.append(cycle['initial_fingerprint'])
        rows=[r for r in cycle.get('tasks',[])if r.get('task_id')==contract['task_id']]
        if len(rows)!=1:raise ValueError('Exactly one original typed source control record required per fresh cycle')
        row=rows[0]
        if (row.get('passed')is not True or row.get('initial_valid')is not True or row.get('ui_reference_matches')is not True or
            row.get('original_initial_view_verified')is not True or row.get('native_reference_verified')is not True or
            row.get('initial_reference')!=ref or row.get('final_reference')!=ref or
            row.get('map_guard_verified')is not True or not row.get('map_geographic_baseline')or
            row.get('checks')!=expected_controls(contract,ref['values'])):
            raise ValueError('Original typed answer/artifact positive and negative controls incomplete')
    if baselines[0]!=baselines[1]:raise ValueError('Native baseline differs between independent deployments')
    geographic=[next(r['map_geographic_baseline']for r in cycle['tasks']if r['task_id']==contract['task_id'])for cycle in cycles]
    if geographic[0]!=geographic[1]:
        raise ValueError('Native geographic baseline differs between independent deployments')

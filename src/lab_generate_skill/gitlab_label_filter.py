"""Native project Issue label filtering with saved-record membership checks.

Unspecified issue status may use any explicitly admitted native status tab.
This does not change the original issue/MR list adapter or infer a label from
an actor's chosen issue.
"""
import re
from urllib.parse import urlsplit,urlunsplit,parse_qs,urlencode
from .gitlab_issuable_list import list_reference,list_checks,read_issuable_list
from .site_database import select_rows


def validate(spec):
    if (not isinstance(spec,dict)or spec.get('kind')!='issues'
        or not isinstance(spec.get('label'),str)or not spec['label'].strip()
        or not isinstance(spec.get('project_path'),str)or not re.fullmatch(r'[\w.-]+(?:/[\w.-]+)+',spec['project_path'])
        or not isinstance(spec.get('username'),str)or not spec['username']
        or not isinstance(spec.get('allowed_states'),list)or not spec['allowed_states']
        or len(set(spec['allowed_states']))!=len(spec['allowed_states'])
        or not set(spec['allowed_states'])<={'opened','closed','all'}):
        raise ValueError('Explicit issue label, project, account and allowed states required')


def reference(site,spec):
    validate(spec)
    native=list_reference(site,{'kind':'issues','project_path':spec['project_path'],'username':spec['username'],'assigned_to_current_user':False})
    ident=int(native['project']['id']);label="'"+spec['label'].replace("'","''")+"'"
    records=select_rows(site,'SELECT DISTINCT i.id FROM issues i JOIN label_links ll ON ll.target_id=i.id AND ll.target_type=\'Issue\' JOIN labels l ON l.id=ll.label_id WHERE i.project_id='+str(ident)+' AND l.title='+label+' ORDER BY i.id')
    ids={r['id']for r in records}
    rows=[r for r in native['rows']if r['id']in ids]
    if len(rows)!=len(ids):raise ValueError('Label membership escapes the accessible project')
    return {'user_id':native['user_id'],'username':native['username'],'project':native['project'],'rows':rows}


def verify_reference(site,spec):
    if reference(site,spec)!=spec['reference']:raise ValueError('Pinned native labeled issue set changed')


def read_labeled_list(page):
    start=page.url;state=read_issuable_list(page)
    extra=page.evaluate(r'''() => ({url:location.href,
        tokens:[...new Set([...document.querySelectorAll('[class*="filtered-search"],[class*="gl-token"]')]
            .filter(e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden')
            .map(e=>e.innerText.trim().replace(/\s+/g,' ')).filter(Boolean))]})''')
    if start!=extra['url']:raise ValueError('Issue list navigated during capture')
    return {**extra,'list':state}


def checks(spec,state):
    validate(spec)
    if (not isinstance(state,dict)or not isinstance(state.get('url'),str)or not isinstance(state.get('list'),dict)
        or not isinstance(state.get('tokens'),list)or any(not isinstance(t,str)for t in state['tokens'])):
        raise ValueError('Missing native labeled-list capture')
    u=urlsplit(state['url']);params=parse_qs(u.query,keep_blank_values=True)
    requested=params.get('state',['opened'])
    selected=requested[0]if len(requested)==1 and requested[0]in spec['allowed_states']else spec['allowed_states'][0]
    allowed=len(requested)==1 and requested[0]in spec['allowed_states']
    labels=params.pop('label_name[]',[])
    tokens=set()
    for text in state['tokens']:
        m=re.fullmatch(r'Label\s*=\s*~?(.+?)\s*(?:×)?',text)
        if m:tokens.add(m[1])
    native_spec={'kind':'issues','project_path':spec['project_path'],'username':spec['username'],
        'state':selected,'reference':spec['reference']}
    url=urlunsplit((u.scheme,u.netloc,u.path,urlencode(params,doseq=True),u.fragment))
    return {**list_checks(native_spec,state['list'],url),
        'allowed_issue_status':allowed,
        'requested_issue_label_applied':labels==[spec['label']]and tokens=={spec['label']},
        'labeled_project_identity':state['list'].get('project_ids')==[str(spec['reference']['project']['id'])]}


FEEDBACK={'allowed_issue_status':'The selected native issue status is allowed by the task.',
    'requested_issue_label_applied':'The requested label is applied in the native issue filter.',
    'labeled_project_identity':'The issue list belongs to the requested project.'}

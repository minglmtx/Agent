"""Private native browser clipboard artifacts; never infer copying from an answer."""
import hashlib
import re
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION='gitlab-clipboard-v1'
ADMISSION_VERSION='gitlab-clipboard-admission-v1'


def validate(c):
    s=c.get('clipboard')
    if c.get('domain')!='gitlab' or not isinstance(s,dict) or set(s)!={'kind','project','project_id','expected'}:
        raise ValueError('Explicit native clipboard target required')
    if s['kind'] not in ('project_id','latest_commit') or type(s['project_id']) is not int or s['project_id']<=0:
        raise ValueError('Unsupported clipboard target')
    if not isinstance(s['project'],str) or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+',s['project']):
        raise ValueError('Invalid native project path')
    pattern=r'[1-9][0-9]*' if s['kind']=='project_id' else r'[0-9a-f]{40}'
    if not isinstance(s['expected'],str) or not re.fullmatch(pattern,s['expected']):raise ValueError('Invalid clipboard reference')


def reference(site,c):
    validate(c);s=c['clipboard'];ident=s['project_id']
    if select_rows(site,f"SELECT path FROM routes WHERE source_type='Project' AND source_id={ident}")!=[{'path':s['project']}]:
        raise ValueError('Native project identity differs')
    if s['kind']=='project_id':value=str(ident)
    else:
        digest=hashlib.sha256(str(ident).encode()).hexdigest()
        repo='/var/opt/gitlab/git-data/repositories/@hashed/'+digest[:2]+'/'+digest[2:4]+'/'+digest+'.git'
        value=site.command(['/opt/gitlab/embedded/bin/git','--git-dir='+repo,'rev-parse','HEAD'],capture_output=True,text=True,timeout=45).stdout.strip()
    if value!=s['expected']:raise ValueError('Independent clipboard reference changed')
    return value


def read(page):
    value=page.evaluate('navigator.clipboard.readText()')
    if not isinstance(value,str):raise ValueError('Clipboard read failed')
    return {'value':value}


def prepare(page,origin):
    """Only the disposable local browser context, never the desktop clipboard."""
    page.context.grant_permissions(['clipboard-read','clipboard-write'],origin=origin)
    page.evaluate("navigator.clipboard.writeText('')")
    state=read(page)
    if state!={'value':''}:raise ValueError('Clipboard reset failed')
    return state


def fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','clipboard','heldout_quarantine','start_revision','goal_revision')})


def evaluate(c,page,initial,final,*,site_origin,runtime_error=None):
    validate(c)
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    if initial!={'value':''}:return unknown('Missing or dirty clipboard baseline')
    if not isinstance(final,dict) or not isinstance(final.get('value'),str):return unknown('Clipboard artifact was not captured')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:
        return unknown('Missing terminal page or transport/server error')
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
            'requested_value_copied':final['value']==c['clipboard']['expected']}
    ok=all(checks.values())
    return {'version':VERSION,'status':'success' if ok else 'failure','reward':float(ok),'checks':checks,'reason':None}


def feedback(j):
    descriptions={'page_valid':'The final document is a valid local website page.',
                  'requested_value_copied':'The browser clipboard contains the value requested by the task.'}
    return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),
            'checks':[{'name':k,'passed':v,'condition':descriptions[k]} for k,v in j['checks'].items()],
            'action_sequence_provided':False,'reference_values_provided':False}


def expected_controls():
    return {'no_op':'failure','navigation_only':'failure','positive':'success','saved_then_home':'success',
            'wrong_project_copy':'failure','404':'failure','login':'failure'}


def require_admission(c,proof):
    validate(c)
    if c.get('heldout_quarantine') or proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(c):
        raise ValueError('Quarantined or stale clipboard proof')
    cycles=proof.get('cycles',[])
    if not proof.get('passed') or len(cycles)!=2:raise ValueError('Two independent clipboard control instances required')
    for r in cycles:
        if not r.get('passed') or r.get('checks')!=expected_controls() or r.get('initial_state')!={'value':''} or r.get('reference')!=c['clipboard']['expected']:
            raise ValueError('Clipboard controls incomplete')
        if r.get('reset_state')!={'value':''} or not r.get('initial_fingerprint') or r['initial_fingerprint']!=r.get('final_fingerprint'):
            raise ValueError('Clipboard or website reset failed')
    if cycles[0]['initial_fingerprint']!=cycles[1]['initial_fingerprint']:raise ValueError('Independent website baselines differ')

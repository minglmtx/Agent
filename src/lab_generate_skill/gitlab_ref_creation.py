"""Private persisted Git branch/tag creation conditions.

Unspecified names remain free choices. A form, success message or actor claim
cannot replace a new Git reference. No reference values are actor instructions.
"""
import hashlib,re
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION='gitlab-ref-creation-v1'
ADMISSION_VERSION='gitlab-ref-creation-admission-v1'


def validate(c):
    s=c.get('ref_creation')
    if c.get('domain')!='gitlab' or not isinstance(s,dict) or set(s)!={'kind','project','project_id','source_ref'}:
        raise ValueError('Explicit repository ref-creation specification required')
    if s['kind'] not in ('branch','tag') or type(s['project_id']) is not int or s['project_id']<=0:
        raise ValueError('Unsupported repository ref creation')
    if not isinstance(s['project'],str) or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+',s['project']):
        raise ValueError('Invalid native project path')
    if s['source_ref'] is not None and (not isinstance(s['source_ref'],str) or not s['source_ref'].startswith('refs/heads/') or '..' in s['source_ref']):
        raise ValueError('Only an explicit existing source branch is supported')


def read_state(site,c):
    validate(c);s=c['ref_creation'];ident=s['project_id']
    if select_rows(site,f"SELECT path FROM routes WHERE source_type='Project' AND source_id={ident}")!=[{'path':s['project']}]:
        raise ValueError('Native repository identity differs')
    digest=hashlib.sha256(str(ident).encode()).hexdigest()
    repo='/var/opt/gitlab/git-data/repositories/@hashed/'+digest[:2]+'/'+digest[2:4]+'/'+digest+'.git'
    def git(*args):return site.command(['/opt/gitlab/embedded/bin/git','--git-dir='+repo,*args],capture_output=True,text=True,timeout=45).stdout
    refs={}
    for line in git('for-each-ref','--format=%(refname)%09%(objectname)%09%(*objectname)','refs/heads/','refs/tags/').splitlines():
        name,sha,peeled=line.split('\t')
        if not re.fullmatch('[0-9a-f]{40}',sha) or name in refs:raise ValueError('Malformed native reference inventory')
        resolved=peeled or sha
        if not re.fullmatch('[0-9a-f]{40}',resolved):raise ValueError('Malformed native peeled reference')
        refs[name]={'object':sha,'commit':resolved}
    commits=sorted(set(git('rev-list','--all').splitlines()))
    if any(not re.fullmatch('[0-9a-f]{40}',v) for v in commits):raise ValueError('Malformed repository history')
    return {'project_id':ident,'project':s['project'],'refs':refs,'commits':commits}


def validate_initial(c,state):
    validate(c);s=c['ref_creation']
    if not isinstance(state,dict) or state.get('project_id')!=s['project_id'] or state.get('project')!=s['project'] or not isinstance(state.get('refs'),dict) or not state.get('commits'):
        raise ValueError('Missing repository baseline')
    if s['source_ref'] and s['source_ref'] not in state['refs']:raise ValueError('Requested source branch absent')


def evaluate(c,page,initial,final,*,site_origin,runtime_error=None):
    validate(c)
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    try:validate_initial(c,initial)
    except ValueError:return unknown('Missing or inconsistent repository state')
    if (not isinstance(final,dict) or final.get('project_id')!=initial['project_id'] or final.get('project')!=initial['project']
        or not isinstance(final.get('refs'),dict) or not isinstance(final.get('commits'),list)
        or any(not isinstance(v,dict) for v in final['refs'].values())):
        return unknown('Missing or inconsistent terminal repository state')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:
        return unknown('Missing terminal page or transport/server error')
    before,after=initial['refs'],final['refs'];added=set(after)-set(before)
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
            'existing_refs_unchanged':all(after.get(k)==v for k,v in before.items()),
            'existing_commit_history_unchanged':initial['commits']==final['commits'],
            'one_new_ref_saved':len(added)==1}
    if len(added)==1:
        name=next(iter(added));new=after[name];s=c['ref_creation']
        checks['requested_ref_kind']=name.startswith('refs/heads/' if s['kind']=='branch' else 'refs/tags/')
        checks['source_commit_matches']=(new.get('commit')==before[s['source_ref']]['commit'] if s['source_ref'] else new.get('commit') in initial['commits'])
    ok=all(checks.values())
    return {'version':VERSION,'status':'success' if ok else 'failure','reward':float(ok),'checks':checks,'reason':None}


def feedback(j):
    meanings={'page_valid':'The final page is a valid local website document.',
        'existing_refs_unchanged':'Existing branches and tags remain unchanged.',
        'existing_commit_history_unchanged':'Existing repository history is preserved without unrelated new commits.',
        'one_new_ref_saved':'Exactly one new branch or tag has actually been saved.',
        'requested_ref_kind':'The saved reference has the type requested in the task.',
        'source_commit_matches':'The new reference points to an existing commit and honors any source branch specified in the task.'}
    return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),
        'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in j['checks'].items()],
        'action_sequence_provided':False,'reference_values_provided':False}


def fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','ref_creation','heldout_quarantine','start_revision','goal_revision')})


def expected_controls(c):
    validate(c)
    checks={k:'failure' for k in ('no_op','filled_unsaved','wrong_kind','404','login')}
    if c['ref_creation']['source_ref']:checks['wrong_source']='failure'
    return checks|{'positive':'success','saved_then_home':'success'}


def require_admission(c,proof):
    validate(c)
    if c.get('heldout_quarantine') or proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(c):
        raise ValueError('Quarantined or stale repository write proof')
    cycles=proof.get('cycles',[])
    if not proof.get('passed') or len(cycles)!=2:raise ValueError('Two independent native reference controls required')
    for r in cycles:
        validate_initial(c,r.get('initial_state'))
        if not r.get('passed') or not r.get('initial_valid') or r.get('checks')!=expected_controls(c) or r.get('restored_state')!=r['initial_state']:
            raise ValueError('Reference controls or restoration incomplete')
        negatives=['wrong_kind']+(['wrong_source'] if c['ref_creation']['source_ref'] else [])
        if any(r.get('isolated_negatives',{}).get(k) is not True for k in negatives):raise ValueError('Independent wrong-kind/source conditions not isolated')
        if not r.get('initial_fingerprint') or r['initial_fingerprint']!=r.get('final_fingerprint'):raise ValueError('Protected website state changed')
    if cycles[0]['initial_state']!=cycles[1]['initial_state'] or cycles[0]['initial_fingerprint']!=cycles[1]['initial_fingerprint']:
        raise ValueError('Independent repository reset baselines differ')

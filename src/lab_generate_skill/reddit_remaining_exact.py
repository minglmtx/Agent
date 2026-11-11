"""Optional exact forum/Wiki/subscription derivative proof compatibility gate.

Legacy Wiki/subscription evaluation remains available unchanged. This gate adds
whole-site restore and all-account subscription integrity; it does not decide
open writing quality or claim equivalence to the original source goals.
"""
from . import reddit_exact_forum as forum
from . import site_wiki_rules as wiki
from . import site_membership_rules as membership
from .site_database import select_rows
from .reddit_protected_chunks import VERSION as PROTECTION_VERSION,require_restored_proof


def read_state(site,username,c,baseline=None):
    if c.get('exact_forum_creation'):return forum.state(site,username,baseline)
    if c.get('wiki'):return wiki.wiki_state(site,username)
    return membership.membership_state(site,username)


def subscriptions(site):
    return [r['row']for r in select_rows(site,'SELECT row_to_json(s) AS row FROM forum_subscriptions s ORDER BY user_id,forum_id,id')]


def validate_subscription_rows(rows):
    if not isinstance(rows,list):raise ValueError('Native all-account subscriptions required')
    keys=[]
    for r in rows:
        if(not isinstance(r,dict)or type(r.get('user_id'))is not int or r['user_id']<=0 or type(r.get('forum_id'))is not int or r['forum_id']<=0
           or not isinstance(r.get('id'),str)or not isinstance(r.get('subscribed_at'),str)):raise ValueError('Malformed saved subscription row')
        from uuid import UUID
        if str(UUID(r['id']))!=r['id']:raise ValueError('Exact native subscription UUID required')
        from datetime import datetime
        timestamp=datetime.fromisoformat(r['subscribed_at'].replace('Z','+00:00'))
        if timestamp.tzinfo is None or timestamp.utcoffset()is None:raise ValueError('Native subscription timestamp timezone required')
        keys.append((r['user_id'],r['forum_id']))
    if len(set(keys))!=len(keys):raise ValueError('Ambiguous native subscription identity')


def all_account_checks(c,initial,final,uid):
    validate_subscription_rows(initial);validate_subscription_rows(final)
    ident=c['membership']['object_id'];key=(uid,ident)
    before={(r['user_id'],r['forum_id']):r for r in initial};after={(r['user_id'],r['forum_id']):r for r in final}
    return {'all_unrelated_account_subscriptions_unchanged':{k:v for k,v in before.items()if k!=key}=={k:v for k,v in after.items()if k!=key},
            'exact_task_account_subscription':(key in after)==c['membership']['desired_present']}


def evaluate(c,page,initial,final,*,site_origin,all_before=None,all_after=None):
    if c.get('exact_forum_creation'):return forum.evaluate(c,page,initial,final,site_origin=site_origin)
    if c.get('wiki'):return wiki.evaluate_wiki(c,page,initial,final,site_origin=site_origin)
    result=membership.evaluate_membership(c,page,initial,final,site_origin=site_origin)
    if result['status']=='unknown':return result
    try:checks=all_account_checks(c,all_before,all_after,initial['user_id'])
    except(ValueError,TypeError,KeyError):return result|{'status':'unknown','reward':None,'checks':{},'reason':'Missing or malformed all-account subscription evidence'}
    checks=result['checks']|checks;success=all(checks.values())
    return result|{'checks':checks,'status':'success'if success else'failure','reward':float(success)}


def expected_controls(c):
    if c.get('exact_forum_creation'):return forum.expected_controls(c)
    if c.get('wiki'):return wiki.expected_controls(c)
    return {'no_op':'failure','wrong_object':'failure','positive':'success','404':'failure'}


def proof(c,cycles):
    if c.get('exact_forum_creation'):
        version=forum.ADMISSION_VERSION;key='version';fingerprint=forum.fingerprint(c)
    elif c.get('wiki'):
        version=wiki.ADMISSION_VERSION;key='admission_version';fingerprint=wiki.contract_fingerprint(c)
    else:
        version=membership.ADMISSION_VERSION;key='admission_version';fingerprint=membership.contract_fingerprint(c)
    return {key:version,'contract_fingerprint':fingerprint,'passed':all(r.get('passed')is True for r in cycles),
            'cycles':cycles,'api_calls':0,'actor_attempts':0,'reset_mode':'two_fresh_sites_restored_per_source',
            'whole_native_restoration_required':True,'protection_version':PROTECTION_VERSION}


def require_admission(c,p):
    require_restored_proof(p)
    if c.get('exact_forum_creation'):forum.require_admission(c,p)
    elif c.get('wiki'):wiki.require_wiki_admission(c,p)
    else:membership.require_membership_admission(c,p)
    if(p.get('api_calls')!=0 or p.get('actor_attempts')!=0 or p.get('whole_native_restoration_required')is not True
       or p.get('reset_mode')!='two_fresh_sites_restored_per_source'or p.get('protection_version')!=PROTECTION_VERSION):raise ValueError('Whole native restore protocol required')
    rows=p['cycles']
    for r in rows:
        if(r.get('protection_version')!=PROTECTION_VERSION or not isinstance(r.get('private_protected_before'),dict)or 'users'not in r['private_protected_before']or not r.get('initial_valid')or not r.get('restored')or r.get('initial_state')!=r.get('final_state')or not r.get('private_protected_before')
           or r['private_protected_before']!=r.get('private_protected_after')or not r.get('initial_fingerprint')or r['initial_fingerprint']!=r.get('final_fingerprint')):
            raise ValueError('Whole protected native state not restored')
        if c.get('membership'):
            validate_subscription_rows(r.get('all_account_initial'));validate_subscription_rows(r.get('all_account_final'))
            if(r['all_account_initial']!=r['all_account_final']or r.get('extended_checks')!={'login':'failure'}):raise ValueError('All-account reset and anonymous control required')
    if(rows[0]['initial_state']!=rows[1]['initial_state']or rows[0]['private_protected_before']!=rows[1]['private_protected_before']or rows[0]['initial_fingerprint']!=rows[1]['initial_fingerprint']):raise ValueError('Fresh native baselines differ')
    if c.get('membership')and rows[0]['all_account_initial']!=rows[1]['all_account_initial']:raise ValueError('Fresh all-account subscription baseline differs')

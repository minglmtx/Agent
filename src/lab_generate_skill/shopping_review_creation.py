"""Native persisted rating/title evaluation; no prose-quality approximation.

All DB references remain private. Pending moderation counts as submitted, not
published. Generic creative-review goals require a separately defined scope.
"""
import hashlib
import json
from bisect import bisect_right
from .site_database import select_rows
from .reddit_submission import id_ranges
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION='shopping-review-creation-v1'
ADMISSION_VERSION='shopping-review-creation-admission-v1'


def validate_contract(c):
    s=c['review_creation']
    if c.get('domain')!='shopping' or set(s)!={'product_id','stars','title'}:
        raise ValueError('Unsupported review creation conditions')
    if type(s['product_id']) is not int or s['product_id']<=0 or type(s['stars']) is not int or not 1<=s['stars']<=5:
        raise ValueError('An explicit product and requested rating are required')
    if s['title'] is not None and (not isinstance(s['title'],str) or not s['title'].strip()):
        raise ValueError('Invalid requested review title')


def fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','review_creation','heldout_quarantine','start_revision','goal_revision')})


def digest(rows):
    return {'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}


def partition_rows(rows,key,ranges):
    """Preserve native order, allowing imported IDs with gaps and low new IDs."""
    starts=[lo for lo,hi in ranges];ends=[hi for lo,hi in ranges]
    if any(type(lo) is not int or type(hi) is not int or not 0<lo<=hi for lo,hi in ranges) or any(starts[i]<=ends[i-1] for i in range(1,len(ranges))):
        raise ValueError('Malformed native ID baseline')
    old=[];added=[]
    for row in rows:
        ident=row[key];i=bisect_right(starts,ident)-1
        (old if i>=0 and ident<=ends[i] else added).append(row)
    return old,added


def review_state(site,email,baseline=None):
    quoted="'"+email.replace("'","''")+"'"
    accounts=select_rows(site,'SELECT entity_id FROM customer_entity WHERE email='+quoted)
    if len(accounts)!=1:raise ValueError('Missing or ambiguous task account')
    out={'account_id':accounts[0]['entity_id']}
    queries={
        'reviews':('review_id','SELECT r.review_id,r.entity_pk_value,r.status_id,d.customer_id,d.title,d.detail,d.nickname '
            'FROM review r JOIN review_detail d ON d.review_id=r.review_id ORDER BY r.review_id'),
        'votes':('vote_id','SELECT vote_id,option_id,review_id,rating_id,value,percent,customer_id FROM rating_option_vote ORDER BY vote_id')}
    for key,(pk,sql) in queries.items():
        rows=select_rows(site,sql,stream=True)
        ranges=id_ranges([r[pk] for r in rows]) if baseline is None else baseline[key]['known_id_ranges']
        old,added=partition_rows(rows,pk,ranges)
        out[key]={'known_id_ranges':ranges,'protected':digest(old),'added':added}
    return out


def validate_initial(c,state):
    validate_contract(c)
    if type(state.get('account_id')) is not int or any(state[k]['added'] for k in ('reviews','votes')):
        raise ValueError('Invalid review baseline')


def evaluate_review(c,page,initial,final,*,site_origin,runtime_error=None):
    validate_contract(c)
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:
        return unknown('Missing terminal page or transport/server error')
    if not initial or not final or initial.get('account_id')!=final.get('account_id') or any(initial[k]['known_id_ranges']!=final[k]['known_id_ranges'] for k in ('reviews','votes')):
        return unknown('Missing or mismatched review baseline')
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
        'existing_reviews_unchanged':all(initial[k]['protected']==final[k]['protected'] for k in ('reviews','votes')),
        'one_review_saved':len(final['reviews']['added'])==1}
    if checks['one_review_saved']:
        r=final['reviews']['added'][0];votes=final['votes']['added'];s=c['review_creation']
        checks.update(correct_product=r['entity_pk_value']==s['product_id'],correct_author=r['customer_id']==initial['account_id'],
            submission_accepted=r['status_id'] in (1,2),
            required_text_saved=all(isinstance(r.get(k),str) and bool(r[k].strip()) for k in ('title','detail','nickname')),
            requested_rating=bool(votes) and len({v['rating_id'] for v in votes})==len(votes) and all(
                v['review_id']==r['review_id'] and v['customer_id']==initial['account_id'] and v['value']==s['stars'] and v['percent']==s['stars']*20 for v in votes))
        if s['title'] is not None:checks['requested_title']=r['title']==s['title']
    passed=all(checks.values())
    return {'version':VERSION,'status':'success' if passed else 'failure','reward':float(passed),'checks':checks,'reason':None}


def feedback(j):
    meanings={'page_valid':'The final page is valid on the task website.',
        'existing_reviews_unchanged':'Existing reviews and ratings remain unchanged.',
        'one_review_saved':'One new review has actually been saved.',
        'correct_product':'The review belongs to the requested product.',
        'correct_author':'The review belongs to the task account.',
        'submission_accepted':'The review is submitted or approved, not rejected.',
        'required_text_saved':'Required native form text fields are saved and nonempty.',
        'requested_rating':'The saved rating matches the requested number of stars.',
        'requested_title':'The saved title matches the title requested in the task.'}
    return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),
        'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in j['checks'].items()],
        'action_sequence_provided':False,'reference_values_provided':False}


def expected_controls(c):
    names=['no_op','filled_unsaved','wrong_product','wrong_rating','404','login']
    if c['review_creation']['title'] is not None:names.append('wrong_title')
    return dict.fromkeys(names,'failure')|{'positive':'success','saved_then_home':'success'}


def require_admission(c,proof):
    validate_contract(c)
    if c.get('heldout_quarantine') or proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(c):
        raise ValueError('Quarantined or stale review admission')
    rows=proof.get('cycles',[])
    if not proof.get('passed') or len(rows)!=2:raise ValueError('Two independent review controls required')
    for r in rows:
        validate_initial(c,r.get('initial_state',{}))
        if not r.get('passed') or not r.get('initial_valid') or r.get('checks')!=expected_controls(c):
            raise ValueError('Incomplete review controls')
        if not r.get('restored') or r['initial_state']!=r.get('final_state') or not r.get('initial_fingerprint') or r['initial_fingerprint']!=r.get('final_fingerprint'):
            raise ValueError('Review fixture reset failed')
    if rows[0]['initial_state']!=rows[1]['initial_state'] or rows[0]['initial_fingerprint']!=rows[1]['initial_fingerprint']:
        raise ValueError('Independent review baselines differ')

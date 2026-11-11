"""Terminal vote checks against the authenticated account's persisted records."""
import hashlib
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION = 'site-vote-v1'
ADMISSION_VERSION = 'site-vote-admission-v2'


def vote_state(site, username):
    if site.domain != 'reddit':
        raise ValueError('Vote adapter requires Reddit')
    users = select_rows(site, "SELECT id FROM users WHERE username='" + username.replace("'", "''") + "'")
    if len(users) != 1:
        raise ValueError('Missing or ambiguous vote account')
    uid = int(users[0]['id'])
    state = {'user_id': uid}
    for kind in ('submission', 'comment'):
        rows = select_rows(site, f'SELECT {kind}_id AS object_id, CASE WHEN upvote THEN 1 ELSE -1 END AS direction FROM {kind}_votes WHERE user_id={uid} ORDER BY {kind}_id')
        if len({r['object_id'] for r in rows}) != len(rows):
            raise ValueError('Duplicate account vote rows')
        state[kind] = rows
    return state


def target_reference(site, c):
    s = c['vote']; ident = int(s['object_id'])
    if s['kind'] == 'submission':
        rows = select_rows(site, f'SELECT id,title,forum_id,net_score FROM submissions WHERE id={ident}')
        if len(rows) != 1 or rows[0]['title'] != s['title'] or rows[0]['forum_id'] != s['forum_id']:
            raise ValueError('Vote target identity differs from bound snapshot')
    elif s['kind']=='comment':
        rows=select_rows(site,f'SELECT c.id,c.submission_id,c.body,c.net_score,u.username FROM comments c JOIN users u ON c.user_id=u.id WHERE c.id={ident}')
        if len(rows)!=1 or rows[0]['username']!=s['username'] or rows[0]['submission_id']!=s['submission_id'] or hashlib.sha256(rows[0]['body'].encode()).hexdigest()!=s['body_sha256']:
            raise ValueError('Comment identity differs from fixed initial-page binding')
        rows[0]['body_sha256']=hashlib.sha256(rows[0].pop('body').encode()).hexdigest()
    else:raise ValueError('Unsupported vote target type')
    return rows[0]


def direction(state, kind, ident):
    rows = [r for r in state[kind] if r['object_id'] == ident]
    if len(rows) > 1:
        raise ValueError('Duplicate vote identity')
    return rows[0]['direction'] if rows else 0


def contract_fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','vote','heldout_quarantine','start_revision','goal_revision')})


def validate_initial(c, state):
    s = c['vote']
    if s['kind'] not in ('submission', 'comment') or set(s['allowed_directions']) not in ({1},{-1},{-1,1}):
        raise ValueError('Explicit vote kind and allowed directions required')
    if type(s['object_id']) is not int or s['object_id'] <= 0:
        raise ValueError('Explicit positive object ID required')
    if direction(state, s['kind'], s['object_id']) in s['allowed_directions']:
        raise ValueError('Vote target already satisfies goal at reset')


def evaluate_vote(c, page, initial, final, *, site_origin, runtime_error=None):
    def unknown(reason):
        return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:
        return unknown('Environment or inference error')
    if not initial or not final or initial.get('user_id') != final.get('user_id'):
        return unknown('Missing or changed vote account')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or page['http_status'] < 200 or page['http_status'] >= 500:
        return unknown('Missing terminal page or transport/server failure')
    s=c['vote']; kind=s['kind']; ident=s['object_id']
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
            'requested_vote_saved':direction(final,kind,ident) in s['allowed_directions']}
    def unrelated(state):
        return {k:[r for r in state[k] if not (k==kind and r['object_id']==ident)] for k in ('submission','comment')}
    checks['other_votes_unchanged']=unrelated(initial)==unrelated(final)
    ok=all(checks.values())
    return {'version':VERSION,'status':'success' if ok else 'failure','reward':float(ok),'checks':checks,'reason':None}


def vote_feedback(judgment):
    meanings={'page_valid':'The final page is valid on the task website.',
              'requested_vote_saved':'The requested vote is saved for the intended item under the task account.',
              'other_votes_unchanged':'Votes on other posts and comments are unchanged.'}
    return {'status':judgment['status'],'reward':judgment['reward'],'reason':judgment.get('reason'),
            'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in judgment['checks'].items()],
            'action_sequence_provided':False}


def expected_controls(c):
    return {'no_op':'failure','wrong_object':'failure','404':'failure','login':'failure',
            'upvote':'success' if 1 in c['vote']['allowed_directions'] else 'failure',
            'downvote':'success' if -1 in c['vote']['allowed_directions'] else 'failure'}


def require_vote_admission(c, proof):
    if c.get('heldout_quarantine') or proof.get('admission_version') != ADMISSION_VERSION or proof.get('contract_fingerprint') != contract_fingerprint(c):
        raise ValueError('Quarantined source or stale vote admission')
    cycles=proof.get('cycles',[])
    if not proof.get('passed') or len(cycles)!=2 or proof.get('reset_mode')!='fresh_site_per_task_cycle':
        raise ValueError('Two independent vote control/reset cycles required')
    for row in cycles:
        if not row.get('passed') or row.get('checks') != expected_controls(c) or not row.get('restored'):
            raise ValueError('Vote controls or restoration failed')
        validate_initial(c,row['initial_state'])
        if row['initial_state'] != row['final_state']:
            raise ValueError('Account votes were not restored')
    if cycles[0]['initial_state'] != cycles[1]['initial_state'] or cycles[0]['initial_reference'] != cycles[1]['initial_reference']:
        raise ValueError('Vote baseline changed across resets')

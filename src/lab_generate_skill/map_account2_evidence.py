"""Replay original-start, native account and reset evidence without a website."""
import json
from urllib.parse import urlsplit,parse_qs
from lab_generate_skill.map_account_initial import validate_document_start
from lab_generate_skill.map_candidate_start import validate_initial
from lab_generate_skill.map_account_terminal import evaluate_account
from lab_generate_skill.map_account_observation import write_integrity
from lab_generate_skill.map_existing_account_observation import require_anonymous,unchanged_login_state,VERSION as LOGIN_VERSION
from lab_generate_skill.map_account_mail import confirmation_from_message
from lab_generate_skill.map_existing_account_site import OTHER
from lab_generate_skill.source_revision_binding import binding

def origin(url):
    p=urlsplit(url)
    if p.scheme!='http' or p.hostname not in ('127.0.0.1','localhost')or not p.port:raise ValueError('Owned source origin missing')
    return p.scheme+'://'+p.netloc

def initial(c,state):
    local=origin(state['url'])
    if state.get('kind')=='document':validate_document_start(c,local,state)
    elif state.get('kind')=='map':validate_initial(c,local,state['url'],state['view'],state.get('route'))
    else:raise ValueError('Native original-start evidence missing')
    return local

def ordinary(c,before,after,want):
    local=initial(c,before['original_start']);require_anonymous(before['session'],local)
    if after['initial']!=before['account']or after.get('capture_error')is not None:raise ValueError('Account readout changed or missing')
    if after['events']!=['prepare','attach','observe_initial','capture_terminal','close','score_terminal']:raise ValueError('Ordinary lifecycle incomplete')
    protection=after['protection']
    if c['candidate_completion']['family']=='account_signup':
        integrity=write_integrity(before['guard'],protection['guard'],files_unchanged=protection.get('persistent_files_unchanged'),users_unchanged=protection.get('existing_users_unchanged'))
    else:
        integrity=unchanged_login_state(before['guard'],protection['guard'],files_unchanged=protection.get('persistent_files_unchanged'),users_unchanged=protection.get('all_users_unchanged'))
    if integrity is not True or after.get('integrity')is not True:raise ValueError('Protected account state unavailable')
    score=evaluate_account(c['candidate_completion'],initial=before['account'],final=after['final'],session=after['session'],origin=local,integrity=integrity)
    if c['candidate_completion']['family']=='account_login':score=dict(score,version=LOGIN_VERSION)
    if score!=after['judgment']or score['status']!=want:raise ValueError('Raw account judgment disagrees')
    return score

def replay(cfg,data):
    get=lambda name:json.loads(data[name]);report=get('result.json');signup,login=cfg['tasks']
    if not report.get('passed')or report.get('actor_calls')!=0 or report.get('api_calls')!=0:raise ValueError('Completed native controls required')
    if len(report['factories'])!=3 or len({r['state']for r in report['factories']})!=3:raise ValueError('Separate signup, reset and login factories required')
    if not get('termination.json').get('confirmed'):raise ValueError('Archive writers not quiescent')
    for c in (signup,login):
        binding(c)
        if c['split']!='train'or c['heldout_quarantine']is not False:raise ValueError('Training source required')
    results={}
    signup_scores=[]
    for prefix,want in [('signup/noop','failure'),('signup/unsubmitted','failure'),('signup/positive','success'),('signup-reset/ordinary-noop','failure')]:
        signup_scores.append(ordinary(signup,get(prefix+'/account-initial.json'),get(prefix+'/account-terminal.json'),want))
    pos=get('signup/positive/account-terminal.json');pre=get('signup/positive/account-initial.json');local=origin(pre['original_start']['url']);pending=get('signup/positive/unconfirmed.json')
    mid=evaluate_account(signup['candidate_completion'],initial=pre['account'],final=pending['account'],session=pending['session'],origin=local)
    if mid!=pending['judgment']or mid['status']!='failure'or pending['account']['target']['status']!='pending'or pending['account']['target']['email_valid']is not False:raise ValueError('Actual unconfirmed account control missing')
    wrong=get('signup/positive/wrong-account.json');w=evaluate_account(wrong['spec'],initial=wrong['initial'],final=wrong['final'],session=wrong['session'],origin=local)
    if w!=wrong['judgment']or w['status']!='failure'or wrong['session']!=pos['session']or not wrong['session']['native_settings_form']or wrong['spec']['public_account']['email']==signup['candidate_completion']['public_account']['email']:raise ValueError('Native other-identity counterexample invalid')
    private=get('signup/positive/private-reset-session.json');account=signup['candidate_completion']['public_account'];tokens=[]
    for row in pos['mail']:
        raw=data['signup/positive/'+row['artifact']]
        try:mail=confirmation_from_message(raw,recipient=account['email'],display_name=account['display_name'],origin=local)
        except ValueError:continue
        tokens.extend(parse_qs(urlsplit(mail['url']).query).get('confirm_string',[]))
    if private['confirmation_token']not in tokens:raise ValueError('Native confirmation message provenance missing')
    restored=get('signup-reset/result.json');stale=restored['old_session_rejected'];record=report['sources'][signup['source_task_id']]
    if (record.get('dirty_reuse_refused')is not True or record.get('passed')is not True or record['restoration']!=restored
        or any(restored.get(k)is not True for k in ('passed','full_native_baseline_equal','full_account_fingerprint_equal','mail_empty','old_token_absent'))
        or restored['target_absent']!={'captured':True,'target':None}
        or stale.get('http_status')!=200 or stale.get('native_settings_form')is not False or stale.get('path')!='/login'
        or report['factories'][0]['baseline']!=report['factories'][1]['baseline']):raise ValueError('Full source-specific cold restoration missing')
    results[signup['source_task_id']]=dict(passed=True,ordinary_controls=4,additional_native_negatives=2,baseline=cfg['baseline'],full_cold_reset=True)
    native_scores=[]
    for name,want in [('noop','failure'),('unsubmitted','failure'),('wrong-account','failure'),('positive','success'),('after-reset-noop','failure')]:
        prefix='login/native/'+name;b=get(prefix+'/initial.json');r=get(prefix+'/result.json');local=initial(login,b['view']);require_anonymous(b['session'],local)
        if r['initial']!=b['account']or r.get('integrity')is not True or r['guard']['changed']:raise ValueError('Native login baseline changed')
        j=evaluate_account(login['candidate_completion'],initial=r['initial'],final=r['final'],session=r['session'],origin=local)
        if j!=r['judgment']or j['status']!=want:raise ValueError('Native login counterexample differs')
        if name=='wrong-account'and (not r['session']['native_settings_form']or r['session']['email']!=OTHER['email']):raise ValueError('Other account was not authenticated')
        native_scores.append(j)
    for name,want in [('positive','success'),('after-reset-noop','failure')]:
        prefix='login/ordinary/'+name;ordinary(login,get(prefix+'/account-initial.json'),get(prefix+'/account-terminal.json'),want)
    record=report['sources'][login['source_task_id']]
    if record.get('passed')is not True or record.get('full_reset_verified')is not True:raise ValueError('Login reset unavailable')
    results[login['source_task_id']]=dict(passed=True,native_controls=5,ordinary_controls=2,baseline=report['factories'][2]['baseline'],full_reset=True)
    return results

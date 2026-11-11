"""Private persisted newsletter checks, independent of the actor's chosen route.

Both native account and footer subscription forms are allowed. No private email,
expected state, or control action sequence is included in actor observations.
"""
from .site_database import select_rows
from .shopping_account import account_state
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION='shopping-newsletter-v1'
ADMISSION_VERSION='shopping-newsletter-admission-v1'
MAIL_PROFILE='local_sendmail_capture_v1'
COLUMNS='subscriber_id,store_id,customer_id,subscriber_email,subscriber_status'


def validate_contract(c):
    if c.get('domain')!='shopping' or c.get('newsletter')!={'operation':'subscribe','identity':'current_account','mail_profile':MAIL_PROFILE}:
        raise ValueError('Unsupported newsletter contract')


def effective_profile(site):
    if not getattr(site,'capture_mail',False):raise ValueError('Isolated local mail capture required')
    code=r'''require "/var/www/magento2/app/bootstrap.php";
    $b=\Magento\Framework\App\Bootstrap::create(BP,$_SERVER);$o=$b->getObjectManager();
    $s=$o->get(\Magento\Framework\App\Config\ScopeConfigInterface::class);
    $out=[];foreach(['system/smtp/transport','system/smtp/disable','newsletter/subscription/confirm'] as $p){$out[$p]=$s->getValue($p,'store',1);}echo json_encode($out);'''
    import json
    config=json.loads(site.command(['php','-r',code],capture_output=True,text=True,timeout=60).stdout)
    if config['system/smtp/transport']!='sendmail' or str(config['system/smtp/disable']) not in ('0','','None'):
        raise ValueError('Local mail transport is not effective')
    return {'name':MAIL_PROFILE,'store_id':1,'config':config}


def newsletter_state(site,username):
    email="'"+username.replace("'","''")+"'"
    users=select_rows(site,'SELECT entity_id,email FROM customer_entity WHERE email='+email)
    if len(users)!=1:raise ValueError('Missing or ambiguous task account')
    return {'user':users[0],'subscriptions':select_rows(site,'SELECT '+COLUMNS+' FROM newsletter_subscriber ORDER BY subscriber_id'),
            'account':account_state(site,username),'mail_profile':effective_profile(site)}


def target_rows(state):
    return [r for r in state['subscriptions'] if r['subscriber_email']==state['user']['email'] and r['store_id']==state['mail_profile']['store_id']]


def other_rows(state):
    return [r for r in state['subscriptions'] if r not in target_rows(state)]


def validate_initial(c,state):
    validate_contract(c)
    if not isinstance(state,dict) or not isinstance(state.get('subscriptions'),list):raise ValueError('Missing newsletter baseline')
    if state['mail_profile']['name']!=MAIL_PROFILE or state['mail_profile']['store_id']!=1:
        raise ValueError('Unsupported isolated mail profile')
    rows=target_rows(state)
    if len(rows)>1 or any(int(r['subscriber_status'])==1 for r in rows):
        raise ValueError('Ambiguous or already subscribed initial state')


def evaluate_newsletter(c,page,initial,final,*,site_origin,runtime_error=None):
    validate_contract(c)
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    if not initial or not final or initial.get('user')!=final.get('user') or initial.get('mail_profile')!=final.get('mail_profile'):
        return unknown('Missing or changed account/environment binding')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:
        return unknown('Missing terminal observation or server/transport error')
    rows=target_rows(final)
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
            'account_unchanged':initial['account']==final['account'],
            'other_subscriptions_unchanged':other_rows(initial)==other_rows(final),
            'one_target_subscription':len(rows)==1,
            # Native email-only subscriptions can have customer_id 0. The
            # account's exact email and store still bind the requested identity.
            'correct_account':len(rows)==1 and rows[0]['customer_id'] in (0,initial['user']['entity_id']),
            'active_subscription_saved':len(rows)==1 and int(rows[0]['subscriber_status'])==1}
    passed=all(checks.values())
    return {'version':VERSION,'status':'success' if passed else 'failure','reward':float(passed),'checks':checks,'reason':None}


def feedback(j):
    meanings={'page_valid':'The final page is valid on the task website.',
              'account_unchanged':'The existing account and saved addresses are unchanged.',
              'other_subscriptions_unchanged':'Unrelated subscription records are unchanged.',
              'one_target_subscription':'Exactly one subscription record exists for the requested identity.',
              'correct_account':'The subscription belongs to the requested identity.',
              'active_subscription_saved':'The subscription is saved and active, not merely entered or pending.'}
    return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),
            'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in j['checks'].items()],
            'action_sequence_provided':False,'reference_values_provided':False}


def fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','newsletter','heldout_quarantine','start_revision','goal_revision')})


def expected_controls():
    return dict.fromkeys(['no_op','filled_unsaved','wrong_email','unsubscribed','404','login'],'failure')|{
        'positive_account':'success','positive_footer':'success','saved_then_home':'success'}


def require_admission(c,proof):
    validate_contract(c)
    if c.get('heldout_quarantine') or proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(c):
        raise ValueError('Quarantined or stale newsletter proof')
    rows=proof.get('cycles',[])
    if not proof.get('passed') or len(rows)!=2:raise ValueError('Two independent native cycles required')
    for r in rows:
        validate_initial(c,r.get('initial_state'))
        if not r.get('passed') or not r.get('initial_valid') or r.get('checks')!=expected_controls():
            raise ValueError('Newsletter controls incomplete')
        if r.get('initial_state')!=r.get('final_state') or not r.get('restored'):
            raise ValueError('Newsletter fixture cleanup incomplete')
        if not r.get('initial_fingerprint') or r['initial_fingerprint']!=r.get('final_fingerprint'):
            raise ValueError('Protected site records changed')
        if not r.get('local_messages_captured'):raise ValueError('Native local mail capture unverified')
    if rows[0]['initial_state']!=rows[1]['initial_state'] or rows[0]['initial_fingerprint']!=rows[1]['initial_fingerprint']:
        raise ValueError('Fresh reset baseline differs')

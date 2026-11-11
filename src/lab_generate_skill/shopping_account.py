"""Private persisted-address and browser-session completion checks."""
import re
from urllib.parse import urlsplit
from .site_database import select_rows
from .site_query_rules import reference_fingerprint

VERSION='shopping-account-v1.3'
ADMISSION_VERSION='shopping-account-admission-v1'


def account_state(site,username):
    if site.domain!='shopping':raise ValueError('Shopping account adapter only')
    quoted="'"+username.replace("'","''")+"'"
    users=select_rows(site,'SELECT entity_id,firstname,lastname,default_shipping,default_billing FROM customer_entity WHERE email='+quoted)
    if len(users)!=1:raise ValueError('Account missing or ambiguous')
    user=users[0]
    addresses=select_rows(site,'SELECT entity_id,parent_id,firstname,lastname,street,city,region,region_id,country_id,postcode,telephone FROM customer_address_entity WHERE parent_id='+str(int(user['entity_id']))+' ORDER BY entity_id')
    return {'customer':user,'addresses':addresses}



def country_account_state(site,username):
    """Read native address form fields without changing old account proofs.

    Company, fax, name affixes and VAT ID are unrelated to a country change.
    Native update timestamps and generated VAT-validation metadata are not task
    input fields and are deliberately outside this comparison.
    """
    state=account_state(site,username)
    rows=select_rows(site,'SELECT entity_id,company,fax,prefix,middlename,suffix,vat_id FROM customer_address_entity WHERE parent_id='+str(int(state['customer']['entity_id']))+' ORDER BY entity_id')
    by_id={r['entity_id']:r for r in rows}
    if len(by_id)!=len(rows)or set(by_id)!={r['entity_id']for r in state['addresses']}:
        raise ValueError('Native address form-field reference differs from account address identities')
    optional=('company','fax','prefix','middlename','suffix','vat_id')
    for row in rows:
        for key in optional:
            # A blank native text field can be stored as NULL or ''. Their
            # displayed meaning is identical; other strings stay exact.
            if row[key]is None:row[key]=''
            elif not isinstance(row[key],str):raise ValueError('Unexpected native address text-field type')
    state['addresses']=[{**row,**by_id[row['entity_id']]}for row in state['addresses']]
    return state



def validate_country_spec(spec):
    if (not isinstance(spec,dict) or spec.get('kind')!='country' or
            spec.get('region_policy')!='native_country_directory' or
            not isinstance(spec.get('value'),str) or not re.fullmatch('[A-Z]{2}',spec['value']) or
            any(type(spec.get(k))is not int or spec[k]<=0 for k in ('customer_id','address_id'))):
        raise ValueError('Explicit country, account/address identity and native region policy required')
    return spec


def require_country_initial(c,state):
    """Bind the richer live state to the privately verified basic original state."""
    validate_country_spec(c['account_change'])
    reference=c.get('capability_initial_basic_state')
    if not isinstance(reference,dict)or not isinstance(state,dict):
        raise ValueError('Missing native original country account reference')
    if reference.get('customer')!=state.get('customer'):
        raise ValueError('Original country account changed from capability baseline')
    live=state.get('addresses',[]);basic=reference.get('addresses',[])
    if not isinstance(live,list)or not isinstance(basic,list)or len(live)!=len(basic):
        raise ValueError('Original country address set changed')
    for expected,actual in zip(basic,live):
        if not isinstance(expected,dict)or not isinstance(actual,dict)or any(actual.get(k)!=v for k,v in expected.items()):
            raise ValueError('Original country address fields changed from capability baseline')
    target=[r for r in live if r.get('entity_id')==c['account_change']['address_id']]
    if len(target)!=1 or target[0].get('parent_id')!=c['account_change']['customer_id'] or target[0].get('country_id')==c['account_change']['value']:
        raise ValueError('Original target address missing, wrong account or goal already satisfied')
    for row in live:
        if any(k not in row for k in ('company','fax','prefix','middlename','suffix','vat_id')):
            raise ValueError('Native unrelated address form fields unavailable')
    return state


class CountryDirectoryError(ValueError):
    """Safe public schema diagnostics, never SQL or arbitrary raw values."""
    def __init__(self,reason,country,row_count):
        self.schema_diagnostic={'reason':reason,
            'country':country if isinstance(country,str)and re.fullmatch('[A-Z]{2}',country)else None,
            'row_count':row_count if type(row_count)is int else None,
            'required_identity':'region_id', 'code_uniqueness_required':False}
        super().__init__('Native country directory schema error: '+reason)


def canonical_country_directory(directory,country):
    if (not isinstance(directory,dict) or set(directory)!={'country','regions'} or
            directory['country']!=country or not isinstance(directory['regions'],list) or
            not directory['regions']):
        raise CountryDirectoryError('missing_or_malformed_directory',country,len(directory.get('regions',[]))if isinstance(directory,dict)and isinstance(directory.get('regions'),list)else None)
    rows=[]
    for raw in directory['regions']:
        if (not isinstance(raw,dict) or set(raw)!={'region_id','country_id','code','default_name','name'} or
                raw['country_id']!=country or
                any(not isinstance(raw[k],str) or not raw[k].strip() for k in ('code','default_name','name'))):
            raise CountryDirectoryError('incomplete_native_region_fields',country,len(directory['regions']))
        value=raw['region_id']
        if type(value)is int and value>0:pass
        elif isinstance(value,str) and re.fullmatch('[1-9][0-9]*',value):value=int(value)
        else:raise CountryDirectoryError('invalid_native_region_id',country,len(directory['regions']))
        rows.append({**raw,'region_id':value})
    # Magento intentionally reuses codes (US Armed Forces regions use AE).
    # Its native select and saved address identify a region by region_id,
    # not by code. Reject repeated primary identities, never valid shared codes.
    if len({r['region_id']for r in rows})!=len(rows):
        raise CountryDirectoryError('duplicate_native_region_id',country,len(rows))
    return {'country':country,'regions':sorted(rows,key=lambda r:r['region_id'])}


def country_region_reference(site,country):
    if site.domain!='shopping' or not isinstance(country,str) or not re.fullmatch('[A-Z]{2}',country):
        raise ValueError('Explicit native Shopping country required')
    rows=select_rows(site,
        "SELECT r.region_id,r.country_id,r.code,r.default_name,COALESCE(n.name,r.default_name) AS name "
        "FROM directory_country_region r LEFT JOIN directory_country_region_name n "
        "ON n.region_id=r.region_id AND n.locale='en_US' WHERE r.country_id='"+country+"' ORDER BY r.region_id")
    return canonical_country_directory({'country':country,'regions':rows},country)


def country_control_expectations():
    return {'no_op':'failure','unsaved':'failure','wrong_setting':'failure',
            'positive':'success','alternate_province':'success','wrong_country':'failure',
            'wrong_object':'failure','wrong_object_state':'failure','404':'failure','login':'failure'}


def persisted_country_checks(spec,initial,final,directory):
    validate_country_spec(spec)
    directory=canonical_country_directory(directory,spec['value'])
    before=[r for r in initial['addresses'] if r.get('entity_id')==spec['address_id']]
    after=[r for r in final['addresses'] if r.get('entity_id')==spec['address_id']]
    if len(before)!=1 or before[0].get('parent_id')!=spec['customer_id']:
        raise ValueError('Initial country address reference is ambiguous or belongs to another account')
    row=after[0]if len(after)==1 else None
    def identity(value):
        if type(value)is int and value>0:return value
        if isinstance(value,str)and re.fullmatch('[1-9][0-9]*',value):return int(value)
        return None
    region=[r for r in directory['regions'] if row and r['region_id']==identity(row.get('region_id'))]
    valid_region=(len(region)==1 and row.get('country_id')==region[0]['country_id'] and
                  row.get('region')in (region[0]['default_name'],region[0]['name']))
    def unrelated(rows):
        return [{k:v for k,v in r.items() if not(r.get('entity_id')==spec['address_id'] and
                k in ('country_id','region','region_id'))}for r in rows]
    return {
        'address_identity':row is not None and row.get('parent_id')==spec['customer_id'],
        'requested_country_saved':bool(row and before[0].get('country_id')!=spec['value'] and
                                       row.get('country_id')==spec['value']),
        'native_country_region_consistent':bool(valid_region),
        'unrelated_account_fields_unchanged':initial.get('customer')==final.get('customer') and
             unrelated(initial['addresses'])==unrelated(final['addresses']),
    }


def session_state(context,origin):
    """Check protected-page access in the same cookie jar after the actor stops.

    This never authenticates or logs out and is not an actor observation/tool.
    """
    page=context.new_page()
    try:
        response=page.goto(origin+'/customer/account/',wait_until='load',timeout=30000)
        u=urlsplit(page.url);expected=urlsplit(origin)
        if response is None or response.status!=200 or (u.scheme,u.netloc)!=(expected.scheme,expected.netloc):raise ValueError('Cannot verify local account session')
        login=page.locator('form#login-form input[name="login[username]"]').count()==1
        account=page.locator('body.customer-account-index').count()==1
        if u.path.rstrip('/')=='/customer/account/login' and login:return {'authenticated':False,'protected_page':'login_required'}
        if u.path.rstrip('/')=='/customer/account' and account:return {'authenticated':True,'protected_page':'account_accessible'}
        raise ValueError('Protected account request returned an unexpected page')
    finally:page.close()


def evaluate_account(c,page,initial,final,*,site_origin,session=None,runtime_error=None,country_directory=None):
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Runtime failure')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:return unknown('Missing terminal page or server failure')
    if not isinstance(initial,dict) or not isinstance(final,dict) or not isinstance(final.get('addresses'),list):return unknown('Missing account state')
    spec=c['account_change'];kind=spec['kind'];u=urlsplit(page['url']);origin=urlsplit(site_origin)
    checks={'page_valid':(u.scheme,u.netloc)==(origin.scheme,origin.netloc) and 200<=page['http_status']<300 and page.get('error_page') is False,
            'account_identity':initial.get('customer')==final.get('customer') and final.get('customer',{}).get('entity_id')==spec['customer_id']}
    if kind=='logout':
        if not isinstance(session,dict) or type(session.get('authenticated')) is not bool:return unknown('Protected-page session verification unavailable')
        checks.update(session_revoked=session['authenticated'] is False and session.get('protected_page')=='login_required',
                      account_records_unchanged=initial==final)
    elif kind=='street_line1':
        if not isinstance(spec.get('value'),str) or not spec['value']:raise ValueError('Explicit requested street line required')
        before=[r for r in initial['addresses'] if r['entity_id']==spec['address_id']]
        after=[r for r in final['addresses'] if r['entity_id']==spec['address_id']]
        if len(before)!=1:raise ValueError('Initial address reference is ambiguous')
        # Requested-line correctness and unrelated-field integrity are separate
        # conditions. A no-op fails the former but must pass the latter.
        def unrelated(addresses):
            rows=[dict(r) for r in addresses]
            for row in rows:
                if row['entity_id']==spec['address_id']:
                    row['street']='\n'.join(row['street'].split('\n')[1:])
            return rows
        checks.update(address_identity=len(after)==1 and after[0]['parent_id']==spec['customer_id'],
                      requested_address_saved=len(after)==1 and after[0]['street'].split('\n')[0]==spec['value'],
                      unrelated_account_fields_unchanged=initial.get('customer')==final.get('customer') and unrelated(final['addresses'])==unrelated(initial['addresses']))
        checks['page_valid']=checks['page_valid'] and page.get('login_page') is False
    elif kind=='country':
        try:checks.update(persisted_country_checks(spec,initial,final,country_directory))
        except (ValueError,TypeError,KeyError,AttributeError)as exc:return unknown(str(exc))
        checks['page_valid']=checks['page_valid'] and page.get('login_page') is False
    else:raise ValueError('Unsupported account operation')
    status='success' if all(checks.values()) else 'failure'
    return {'version':VERSION,'status':status,'reward':float(status=='success'),'checks':checks,'reason':None}


def contract_fingerprint(c):
    fields=('task_id','source_task_id','domain','goal','start_path','account_change','heldout_quarantine','start_revision')
    if c.get('account_change',{}).get('kind')=='country':fields+=('capability_initial_basic_state',)
    return reference_fingerprint({k:c.get(k)for k in fields})


def require_account_admission(c,proof):
    if c.get('heldout_quarantine'):raise ValueError('Heldout source cannot enter development')
    if proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=contract_fingerprint(c):raise ValueError('Stale account admission')
    cycles=proof.get('cycles',[])
    expected={'no_op':'failure','wrong_setting':'failure','positive':'success','404':'failure'}
    if c['account_change']['kind']=='street_line1':expected.update(unsaved='failure',login='failure')
    elif c['account_change']['kind']=='logout':expected['other_session_logout']='failure'
    elif c['account_change']['kind']=='country':
        validate_country_spec(c['account_change']);expected=country_control_expectations()
    else:raise ValueError('Unsupported account operation')
    if not proof.get('passed') or len(cycles)!=2 or any(not r.get('passed') or not r.get('restored') or r.get('checks')!=expected for r in cycles):raise ValueError('Two independent account control/reset cycles required')
    if not cycles[0].get('initial_state') or cycles[0]['initial_state']!=cycles[1].get('initial_state'):raise ValueError('Account reset mismatch')
    if any(r.get('initial_fingerprint')!=r.get('final_fingerprint') or not r.get('initial_fingerprint') for r in cycles):raise ValueError('Protected records changed')
    if c['account_change']['kind']=='country':
        require_country_initial(c,cycles[0]['initial_state'])
        directories=[canonical_country_directory(r.get('country_directory'),c['account_change']['value'])for r in cycles]
        if (directories[0]!=directories[1]or any(r.get('country_directory_unchanged')is not True or
                r.get('native_country_restore_verified')is not True or
                r.get('wrong_object_native_reference_verified')is not True for r in cycles)):
            raise ValueError('Country admission requires unchanged independent region references, native restoration and actual wrong-object control')



def account_feedback(judgment):
    meanings={'page_valid':'The terminal page is valid on the task website.',
      'account_identity':'The operation belongs to the requested account.',
      'address_identity':'The saved address is the requested address belonging to that account.',
      'requested_address_saved':'The requested address change has been saved.',
      'requested_country_saved':'The requested country has been saved on the target address.',
      'native_country_region_consistent':'The saved province identity and name belong to the saved country.',
      'unrelated_account_fields_unchanged':'Unrelated account and address fields remain unchanged.',
      'session_revoked':'The current browser session no longer has access to the protected account page.',
      'account_records_unchanged':'Account and address records remain unchanged.'}
    return {'status':judgment['status'],'reward':judgment['reward'],'reason':judgment.get('reason'),
      'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in judgment['checks'].items()],
      'action_sequence_provided':False}

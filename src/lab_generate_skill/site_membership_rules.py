"""Saved per-account subscriptions, stars, collections and optional hidden forums."""
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page

VERSION='site-membership-v1'


def membership_state(site,username,collection=None):
    if not isinstance(username,str) or not username:raise ValueError('Missing account binding')
    if site.domain=='reddit' and collection=='hidden_forums':
        from .reddit_hidden_membership import hidden_membership_state
        return hidden_membership_state(site,username)
    quoted="'"+username.replace("'","''")+"'"
    if site.domain=='shopping':
        if collection not in ('wishlist','compare'):raise ValueError('Explicit shopping collection required')
        users=select_rows(site,'SELECT entity_id FROM customer_entity WHERE email='+quoted)
        if len(users)!=1:raise ValueError('Account missing or ambiguous')
        uid=int(users[0]['entity_id'])
        wish=select_rows(site,f'SELECT i.product_id FROM wishlist w JOIN wishlist_item i USING (wishlist_id) WHERE w.customer_id={uid} ORDER BY i.product_id')
        compare=select_rows(site,f'SELECT product_id FROM catalog_compare_item WHERE customer_id={uid} ORDER BY product_id')
        collections={'wishlist':sorted({int(x['product_id']) for x in wish}), 'compare':sorted({int(x['product_id']) for x in compare})}
        return {'user_id':uid,'collection':collection,'memberships':collections[collection],
                'other_collections':{k:v for k,v in collections.items() if k!=collection}}
    users=select_rows(site,'SELECT id,username FROM users WHERE username='+quoted)
    if len(users)!=1:raise ValueError('Account missing or ambiguous')
    uid=int(users[0]['id'])
    table,column={'reddit':('forum_subscriptions','forum_id'),'gitlab':('users_star_projects','project_id')}[site.domain]
    rows=select_rows(site,f'SELECT {column} AS object_id FROM {table} WHERE user_id={uid} ORDER BY {column}')
    return {'user_id':uid,'memberships':sorted({int(r['object_id']) for r in rows})}


def evaluate_membership(contract,page,initial,final,*,site_origin,runtime_error=None):
    if _hidden_contract(contract):
        from .reddit_hidden_membership import evaluate_hidden_membership
        return evaluate_hidden_membership(contract,page,initial,final,site_origin=site_origin,runtime_error=runtime_error)
    def unknown(why):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':why}
    if runtime_error:return unknown('Runtime failure')
    if not initial or not final or initial.get('user_id')!=final.get('user_id'):return unknown('Missing or changed account reference')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or page['http_status']<200 or page['http_status']>=500:return unknown('Missing terminal capture or server failure')
    spec=contract['membership'];ident=spec['object_id']
    if type(ident) is not int or type(spec['desired_present']) is not bool:raise ValueError('Invalid membership condition')
    if contract.get('domain')=='shopping' and (initial.get('collection')!=spec.get('collection') or final.get('collection')!=spec.get('collection')):
        return unknown('Missing or mismatched collection state')
    before=set(initial['memberships']);after=set(final['memberships']);desired=spec['desired_present']
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),'target_membership':(ident in after)==desired,
            'other_memberships_unchanged':(before-{ident})==(after-{ident})}
    if contract.get('domain')=='shopping':checks['other_collections_unchanged']=initial.get('other_collections')==final.get('other_collections')
    status='success' if all(checks.values()) else 'failure'
    return {'version':VERSION,'status':status,'reward':float(status=='success'),'checks':checks,'reason':None}


ADMISSION_VERSION='site-membership-admission-v1'


def _hidden_contract(contract):
    return contract.get('domain')=='reddit' and contract.get('membership',{}).get('collection')=='hidden_forums'


def contract_fingerprint(contract):
    if _hidden_contract(contract):
        from .reddit_hidden_membership import contract_fingerprint as hidden_fingerprint
        return hidden_fingerprint(contract)
    from .site_query_rules import reference_fingerprint
    return reference_fingerprint({k:contract.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','membership','heldout_quarantine','start_revision')})


def validate_target(site,contract):
    if _hidden_contract(contract):
        from .reddit_hidden_membership import verify_reference
        return verify_reference(site,contract)
    spec=contract['membership'];ident=spec['object_id']
    if type(ident) is not int or ident<=0:raise ValueError('Invalid membership target')
    if site.domain=='shopping':
        rows=select_rows(site,f"SELECT v.value AS url_key FROM catalog_product_entity_varchar v JOIN eav_attribute a ON a.attribute_id=v.attribute_id WHERE v.entity_id={ident} AND v.store_id=0 AND a.attribute_code='url_key' AND a.entity_type_id=4")
        if len(rows)!=1 or '/'+rows[0]['url_key']+'.html'!=spec['object_path']:raise ValueError('Product identity mismatch')
        if spec.get('collection') not in ('wishlist','compare'):raise ValueError('Unknown shopping collection')
    elif site.domain=='reddit':
        rows=select_rows(site,f'SELECT name FROM forums WHERE id={ident}')
        if len(rows)!=1 or '/f/'+rows[0]['name']!=spec['object_path']:raise ValueError('Forum identity mismatch')
    else:
        rows=select_rows(site,f"SELECT path FROM routes WHERE source_id={ident} AND source_type='Project'")
        if len(rows)!=1 or '/'+rows[0]['path']!=spec['object_path']:raise ValueError('Project identity mismatch')


def require_membership_admission(contract,proof):
    if _hidden_contract(contract):
        from .reddit_hidden_membership import require_admission
        return require_admission(contract,proof)
    if contract.get('heldout_quarantine'):raise ValueError('Heldout task cannot enter development tests')
    if proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=contract_fingerprint(contract):raise ValueError('Stale membership proof')
    cycles=proof.get('cycles',[])
    expected={'no_op':'failure','wrong_object':'failure','positive':'success','404':'failure'}
    if not proof.get('passed') or len(cycles)!=2 or any(not c.get('passed') or not c.get('restored') or c.get('checks')!=expected for c in cycles):raise ValueError('Two saved membership control/reset cycles required')
    if not cycles[0].get('initial_state') or cycles[0]['initial_state']!=cycles[1].get('initial_state'):raise ValueError('Membership reset mismatch')


def membership_feedback(judgment):
    from .reddit_hidden_membership import VERSION as HIDDEN_VERSION
    if judgment.get('version')==HIDDEN_VERSION:
        from .reddit_hidden_membership import feedback
        return feedback(judgment)
    meanings={'page_valid':'The final page is valid on the task website.','target_membership':'The requested subscription, bookmark or product is saved in the requested collection for the logged-in account.',
              'other_memberships_unchanged':'Unrelated subscriptions or saved items remain unchanged.',
              'other_collections_unchanged':'Other saved product collections remain unchanged.'}
    return {'status':judgment['status'],'reward':judgment['reward'],'reason':judgment.get('reason'),
            'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in judgment['checks'].items()],'action_sequence_provided':False}

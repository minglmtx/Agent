"""Terminal-only native catalog toolbar checks, with independent reset evidence."""
from decimal import Decimal
from .catalog_state import collection_scope
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION='site-catalog-v1'
ADMISSION_VERSION='site-catalog-admission-v1'


def contract_fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','catalog','heldout_quarantine','start_revision','goal_revision')})


def validate_contract(c):
    s=c['catalog'];target=s['target']
    if c['domain']!='shopping' or len(target)!=1 or not set(target)<={'price_directions','limit','mode','page'}:
        raise ValueError('One explicit native catalog operation is required')
    if 'price_directions' in target and (not target['price_directions'] or not set(target['price_directions'])<={'asc','desc'}):
        raise ValueError('Invalid requested price direction')
    if 'mode' in target and target['mode'] not in ('grid','list'):raise ValueError('Invalid requested mode')
    for name in ('page','limit'):
        if name in target and (type(target[name]) is not int or target[name]<=0):raise ValueError('Invalid requested '+name)
    for name in ('collection_path','wrong_collection_path'):
        if not s[name].startswith('/') or s[name].startswith('//'):raise ValueError('Local collection path required')
    if collection_scope(s['collection_path'])==collection_scope(s['wrong_collection_path']):raise ValueError('Distinct negative collection required')


def expected_controls(c):
    labels=['no_op','wrong_object','unchanged_list','404','login']
    if 'price_directions' in c['catalog']['target']:
        return dict.fromkeys(labels,'failure') | {'price_'+d:('success' if d in c['catalog']['target']['price_directions'] else 'failure') for d in ('asc','desc')}
    return dict.fromkeys(labels,'failure') | {'positive':'success'}


def evaluate_catalog(c,page,state,reference,*,site_origin,runtime_error=None):
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    validate_contract(c)
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:
        return unknown('Missing final page or transport/server error')
    if not isinstance(reference,dict) or reference.get('present') is not True:return unknown('Missing catalog reference')
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin)}
    if not isinstance(state,dict) or type(state.get('present')) is not bool:return unknown('Missing terminal catalog capture')
    checks['catalog_present']=state['present']
    if state['present']:
        try:
            checks['correct_collection']=state['scope']==collection_scope(c['catalog']['collection_path'])
            checks['collection_size_unchanged']=state['total']==reference['total']
            limit=state['limit'];number=state['page'];total=state['total'];items=state['items']
            if any(type(v) is not int or v<=0 for v in (limit,number,total)):return unknown('Malformed native catalog counters')
            expected=min(limit,max(0,total-(number-1)*limit))
            checks['rendered_page_consistent']=bool(expected and len(items)==expected and len({r['path'] for r in items})==len(items))
            target=c['catalog']['target']
            for key,value in target.items():
                if key=='price_directions':
                    checks['requested_sort']=state['order']=='price' and state['direction'] in value
                    prices=[Decimal(r['price']) for r in items]
                    if any(not n.is_finite() for n in prices):return unknown('Malformed rendered prices')
                    checks['prices_in_displayed_order']=prices==sorted(prices,reverse=state['direction']=='desc')
                else:checks['requested_'+key]=state[key]==value
            if 'page' in target and reference['page']!=target['page']:
                checks['page_contents_changed']=[r['path'] for r in items]!=[r['path'] for r in reference['items']]
        except (KeyError,TypeError,ValueError,ArithmeticError):return unknown('Incomplete native catalog state')
    ok=all(checks.values())
    return {'version':VERSION,'status':'success' if ok else 'failure','reward':float(ok),'checks':checks,'reason':None}


def catalog_feedback(judgment):
    meanings={'page_valid':'The final page is valid on the task website.',
              'catalog_present':'A product list is displayed.',
              'correct_collection':'The list belongs to the requested category or search with its required filters.',
              'collection_size_unchanged':'The requested collection has not been replaced by a different result set.',
              'rendered_page_consistent':'The visible list contains the number of products indicated by its pagination.',
              'requested_sort':'The list uses the requested price sort and direction.',
              'prices_in_displayed_order':'Actual product prices follow the displayed sort direction.',
              'requested_limit':'The list uses the requested number of products per page.',
              'requested_mode':'The rendered list uses the requested display format.',
              'requested_page':'The requested page number is displayed.',
              'page_contents_changed':'The requested new page displays a different slice of products.'}
    return {'status':judgment['status'],'reward':judgment['reward'],'reason':judgment.get('reason'),
            'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in judgment['checks'].items()],
            'action_sequence_provided':False}


def require_catalog_admission(c,proof):
    validate_contract(c)
    if c.get('heldout_quarantine') or proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=contract_fingerprint(c):
        raise ValueError('Quarantined source or stale catalog admission')
    cycles=proof.get('cycles',[])
    if not proof.get('passed') or len(cycles)!=2:raise ValueError('Two independent catalog control/reset cycles required')
    for r in cycles:
        if not r.get('passed') or r.get('checks')!=expected_controls(c) or not r.get('initial_valid'):
            raise ValueError('Catalog controls failed')
        if not r.get('initial_fingerprint') or r['initial_fingerprint']!=r.get('final_fingerprint'):
            raise ValueError('Catalog controls changed protected records')
    for key in ('initial_fingerprint','initial_catalog','reference'):
        if key not in cycles[0] or cycles[0][key]!=cycles[1].get(key):raise ValueError('Catalog reset baseline changed')

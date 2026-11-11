"""Terminal search/filter result checks against native, isolated reference pages."""
from urllib.parse import urlsplit
from .shopping_search import search_scope
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION = 'site-search-native-keyword-echo-v2'
ADMISSION_VERSION = 'site-search-admission-v1'


def contract_fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','search','heldout_quarantine','start_revision','goal_revision')})


def validate_contract(c):
    s = c['search']
    if c['domain'] != 'shopping' or s['kind'] not in ('advanced','filter','keyword'):
        raise ValueError('Unsupported native search operation')
    for key in ('target_path','wrong_path','control_start_path'):
        p = urlsplit(s[key])
        if p.scheme or p.netloc or not p.path.startswith('/') or p.path.startswith('//') or p.fragment:
            raise ValueError('Local native search paths required')
    if search_scope(s['target_path']) == search_scope(s['wrong_path']):
        raise ValueError('Negative control must use different criteria')
    if s['kind'] == 'advanced':
        fields = s['fields']
        allowed = {'name','sku','description','short_description','price[from]','price[to]'}
        if not fields or not set(fields) <= allowed or any(not isinstance(v,str) or not v for v in fields.values()):
            raise ValueError('Explicit native advanced-search fields required')
        expected = {'path':'/catalogsearch/advanced/result/','filters':{k:[v] for k,v in fields.items()}}
        if search_scope(s['target_path']) != expected:
            raise ValueError('Native control fields and target scope disagree')
    elif s['kind']=='keyword':
        keyword=s.get('keyword')
        if not isinstance(keyword,str) or not keyword.strip() or keyword!=keyword.strip():
            raise ValueError('Explicit nonempty search keyword required')
        if search_scope(s['target_path']) != {'path':'/catalogsearch/result/','filters':{'q':[keyword]}}:
            raise ValueError('Keyword and target scope disagree')
    elif not s.get('filter_label') or not s.get('filter_value'):
        raise ValueError('Explicit native filter identity required')


def expected_controls(c):
    return dict.fromkeys(('no_op','wrong_criteria','url_only','unsubmitted','404','login'),'failure') | {'positive':'success','alternate_view':'success'}


def usable_reference(c, state):
    if not isinstance(state,dict) or state.get('scope') != search_scope(c['search']['target_path']):
        return False
    cat = state.get('catalog',{})
    if c['search']['kind'] == 'advanced' and not state.get('criteria'):return False
    if c['search']['kind'] == 'filter' and not state.get('filters'):return False
    if c['search']['kind'] == 'keyword' and state.get('heading') != "Search results for: '"+c['search']['keyword']+"'":return False
    return (cat.get('present') is True and bool(cat.get('items')) and not state.get('empty_result')) or (
        cat.get('present') is False and state.get('empty_result') is True and
        (bool(state.get('criteria')) or c['search']['kind']=='keyword'))


def native_keyword_echoes_match(state, reference):
    """Compare a native keyword echo while keeping every other scope exact.

    This does not establish result correctness. The independent rendered
    product list, category, criteria, counts and toolbar must still match.
    Advanced-search field values and unrelated headings remain exact.
    """
    actual_scope, requested_scope = state.get('scope'), reference.get('scope')
    if not isinstance(actual_scope,dict) or not isinstance(requested_scope,dict):
        return False
    if actual_scope.get('path') != '/catalogsearch/result/' or requested_scope.get('path') != '/catalogsearch/result/':
        return False
    actual_filters, requested_filters = actual_scope.get('filters'), requested_scope.get('filters')
    if not isinstance(actual_filters,dict) or not isinstance(requested_filters,dict):
        return False
    actual_q, requested_q = actual_filters.get('q'), requested_filters.get('q')
    if not isinstance(actual_q,list) or not isinstance(requested_q,list) or len(actual_q)!=1 or len(requested_q)!=1:
        return False
    if not isinstance(actual_q[0],str) or not isinstance(requested_q[0],str) or not actual_q[0]:
        return False
    if actual_q[0].casefold() != requested_q[0].casefold():
        return False
    if {k:v for k,v in actual_filters.items() if k!='q'} != {k:v for k,v in requested_filters.items() if k!='q'}:
        return False
    return (state.get('heading') == "Search results for: '"+actual_q[0]+"'" and
            reference.get('heading') == "Search results for: '"+requested_q[0]+"'")


def actual_catalog_matches(state, reference, *, native_keyword_echo):
    actual, expected = state.get('catalog'), reference.get('catalog')
    if actual == expected:
        return True
    if not native_keyword_echo or not isinstance(actual,dict) or not isinstance(expected,dict):
        return False
    if actual.get('heading') != state.get('heading') or expected.get('heading') != reference.get('heading'):
        return False
    # Only replace a verified echo of the query. Product names, prices, order,
    # counts, pagination and all other native fields remain exact.
    return {**actual,'heading':expected.get('heading')} == expected


def evaluate_search(c, page, state, reference, *, site_origin, runtime_error=None):
    validate_contract(c)
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:
        return unknown('Missing terminal page or transport/server error')
    if not isinstance(state,dict):return unknown('Missing terminal search capture')
    if not usable_reference(c,reference):return unknown('Missing or invalid independent native search reference')
    keyword_echo = native_keyword_echoes_match(state, reference)
    checks = {'page_valid':valid_initial_page(page,site_origin=site_origin),
              'requested_search_scope':state.get('scope')==reference['scope'] or keyword_echo,
              'native_criteria_match':state.get('criteria')==reference['criteria'] and state.get('filters')==reference['filters'],
              'result_heading_match':state.get('heading')==reference['heading'] or keyword_echo,
              'result_kind_match':state.get('empty_result')==reference['empty_result'] and state.get('catalog',{}).get('present')==reference['catalog']['present']}
    if reference['catalog']['present']:
        # Reference is independently rendered with the terminal toolbar settings.
        # This accepts legitimate page/sort/layout changes without trusting URLs.
        checks['actual_results_match']=actual_catalog_matches(state,reference,native_keyword_echo=keyword_echo)
    ok=all(checks.values())
    return {'version':VERSION,'status':'success' if ok else 'failure','reward':float(ok),'checks':checks,'reason':None}


def search_feedback(j):
    meanings={'page_valid':'The final page is a valid page on the task website.',
              'requested_search_scope':'The final result set uses the requested search or category scope.',
              'native_criteria_match':'The applied criteria displayed by the website match the requested conditions.',
              'result_heading_match':'The displayed result page belongs to the requested collection.',
              'result_kind_match':'The website displays a completed result list or a legitimate empty search result.',
              'actual_results_match':'The actual displayed products and counters match the requested criteria.'}
    return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),
            'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in j['checks'].items()],
            'action_sequence_provided':False}


def require_search_admission(c, proof):
    validate_contract(c)
    from .shopping_search_protection import uses_full_protection
    uses_full_protection(c, proof)
    if c.get('heldout_quarantine') or proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=contract_fingerprint(c):
        raise ValueError('Quarantined source or stale search admission')
    cycles=proof.get('cycles',[])
    if not proof.get('passed') or len(cycles)!=2:raise ValueError('Two independent search/reset cycles required')
    for r in cycles:
        if not r.get('passed') or not r.get('initial_valid') or r.get('checks')!=expected_controls(c):raise ValueError('Search controls failed')
        if not r.get('initial_fingerprint') or r['initial_fingerprint']!=r.get('final_fingerprint'):raise ValueError('Search controls changed protected records')
        if not usable_reference(c,r.get('reference')):raise ValueError('Native reference unavailable')
    for key in ('initial_search','reference','initial_fingerprint'):
        if key not in cycles[0] or cycles[0][key]!=cycles[1].get(key):raise ValueError('Search reset baseline changed')

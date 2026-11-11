"""Candidate completion check for explicitly unfiltered admin listings.

Evidence is passive. Missing capture/unfinished transport is unknown, not an
Actor failure. Pagination and page size are unrestricted. A valid empty list
is accepted. The capture adapter must bind an actual applied server/provider
filter state, not draft text typed into an input.
"""
VERSION='admin-unfiltered-listing-v1'
SOURCE_PATHS={
 '21b56472c09b5af384f8':'/catalog/product/',
 '3f3122e9facc97c4287f':'/catalog/product/',
 '9d081b9f92bfe8923b7a':'/sales/invoice/',
 '288d0528f8245033c650':'/sales/creditmemo/',
 'd165fa1c58233af52006':'/newsletter/problem/',
}

def nonempty(value):
    if value is None or value=='':return False
    if isinstance(value,str):return bool(value.strip())
    if isinstance(value,dict):return any(nonempty(v)for v in value.values())
    if isinstance(value,list):return any(nonempty(v)for v in value)
    return True

def active_filters(params):
    if not isinstance(params,dict):raise ValueError('Applied listing params missing')
    filters=params.get('filters',{})
    if not isinstance(filters,dict):raise ValueError('Applied filters malformed')
    if 'search'in params and not isinstance(params['search'],(str,type(None))):raise ValueError('Search parameter malformed')
    active={k:v for k,v in filters.items()if k!='placeholder'and nonempty(v)}
    if nonempty(params.get('search')):active['search']=params['search']
    return active

def checks(spec,evidence):
    if not isinstance(spec,dict)or spec.get('version')!=VERSION:raise ValueError('Unknown listing scope')
    source=spec.get('source_task_id')
    if source not in SOURCE_PATHS or spec.get('target_path')!=SOURCE_PATHS[source]:raise ValueError('Listing source/path not bound')
    if not isinstance(evidence,dict)or evidence.get('version')!=VERSION:raise ValueError('Listing capture missing')
    if evidence.get('target_path')!=spec['target_path']:raise ValueError('Listing capture belongs to another page')
    for key in ['table_visible','loading','transport_error','data_bound']:
        if type(evidence.get(key))is not bool:raise ValueError('Listing state missing or malformed: '+key)
    if evidence['loading']or evidence['transport_error']or not evidence['data_bound']:raise ValueError('Listing request unfinished, unbound or failed')
    total=evidence.get('total_records');shown=evidence.get('displayed_records')
    if type(total)is not int or type(shown)is not int or not 0<=shown<=total:raise ValueError('Listing counts missing or inconsistent')
    filters=active_filters(evidence.get('applied_params'))
    return {'requested_listing_visible':evidence['table_visible'],
            'listing_data_loaded':evidence['data_bound']and ((total==0 and shown==0)or shown>0),
            'listing_unfiltered':not filters}

def scope_for(source):
    if source not in SOURCE_PATHS:raise ValueError('Source outside the five listing revisions')
    return dict(version=VERSION,source_task_id=source,target_path=SOURCE_PATHS[source])

PROVIDERS={'/catalog/product/':'product_listing.product_listing_data_source',
           '/sales/invoice/':'sales_order_invoice_grid.sales_order_invoice_grid_data_source',
           '/sales/creditmemo/':'sales_order_creditmemo_grid.sales_order_creditmemo_grid_data_source'}
CAPTURE_JS=r'''spec => {
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
 const tables=[...document.querySelectorAll('table.data-grid')].filter(visible);
 const loading=[...document.querySelectorAll('.loading-mask,.admin__data-grid-loading-mask')].some(visible);
 const p=require('uiRegistry').get(spec.provider);
 if(!p)throw new Error('Requested native listing provider is absent');
 const u=x=>typeof x==='function'?x():x;
 const data=u(p.data);if(!data||!Array.isArray(data.items))throw new Error('Native listing data unavailable');
 const table=tables.length===1?tables[0]:null;
 const rows=table?[...table.querySelectorAll('tbody tr.data-row')].filter(visible):[];
 return {version:spec.version,target_path:spec.target_path,table_visible:!!table,
  loading:loading||!!u(p.loading),transport_error:!!u(p.lastError),
  data_bound:!!table&&rows.length===data.items.length,
  total_records:data.totalRecords,displayed_records:rows.length,applied_params:u(p.params),
  provider_name:p.name};
}'''

def _probe_modern(page,spec):
    """Only opted-in tasks capture this evidence; no actions or waits are added."""
    if not spec:return None
    if spec!=scope_for(spec.get('source_task_id')):raise ValueError('Unreviewed listing scope')
    provider=PROVIDERS.get(spec['target_path'])
    if provider is None:
        return {'version':VERSION,'capture_error':'Legacy listing capture not yet qualified'}
    try:
        return page.evaluate(CAPTURE_JS,{**spec,'provider':provider})
    except Exception as exc:
        return {'version':VERSION,'capture_error':type(exc).__name__}

def legacy_response(html):
    """Read server-rendered filters, never the browser's unsubmitted input text."""
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(html,'html.parser');table=soup.select_one('#problemGrid_table');count=soup.select_one('#problemGrid-total-count')
    if table is None or count is None:raise ValueError('Legacy listing identity/count missing')
    text=count.get_text(strip=True).replace(',','')
    if not text.isdigit():raise ValueError('Legacy listing total malformed')
    filters={}
    for field in table.select('thead [name]'):
        name=field.get('name','')
        if not name or name=='queue_start[locale]':continue
        if field.name=='select':
            option=field.select_one('option[selected]') or field.select_one('option');value=option.get('value','')if option else ''
        else:value=field.get('value','')
        if nonempty(value):filters[name]=value
    return dict(total_records=int(text),applied_params={'filters':filters})

def install(page,binding):
    spec=binding['spec'].get('required_listing_scope')
    if not spec or spec['target_path']!='/newsletter/problem/':return
    from urllib.parse import urlsplit
    import re
    page._listing_legacy={'receipt':None,'pending':set()}
    netloc=binding['site_netloc']
    def matches(request):
        u=urlsplit(request.url)
        return u.netloc==netloc and re.fullmatch(r'/admin/newsletter/problem(?:/grid|/index)?(?:/(?:key|filter|page|limit|sort|dir)/[^/]*)*/?',u.path) is not None
    def started(request):
        if matches(request):page._listing_legacy['pending'].add(id(request))
    def finished(request):
        if not matches(request):return
        state=page._listing_legacy;state['pending'].discard(id(request));state['receipt']={'valid':False}
        try:
            response=request.response()
            if response is None or response.status!=200:return
            state['receipt']={'valid':True,**legacy_response(response.text())}
        except Exception as exc:state['receipt']['error']=type(exc).__name__
    def failed(request):
        if matches(request):
            state=page._listing_legacy;state['pending'].discard(id(request));state['receipt']={'valid':False,'error':'request_failed'}
    page.on('request',started);page.on('requestfinished',finished);page.on('requestfailed',failed)

LEGACY_JS=r'''() => {
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
 const table=document.querySelector('#problemGrid_table');
 const rows=table?[...table.querySelectorAll('tbody tr')].filter(e=>visible(e)&&!e.classList.contains('data-grid-tr-no-data')):[];
 const counter=document.querySelector('#problemGrid-total-count');
 return {table_visible:visible(table),loading:[...document.querySelectorAll('.loading-mask,.admin__data-grid-loading-mask')].some(visible),displayed_records:rows.length,total_records:counter?Number(counter.textContent.trim().replaceAll(',','')):null};
}'''
def probe(page,spec):
    if not spec or spec.get('target_path')!='/newsletter/problem/':return _probe_modern(page,spec)
    if spec!=scope_for(spec.get('source_task_id')):raise ValueError('Unreviewed listing scope')
    try:
        state=getattr(page,'_listing_legacy',{});receipt=state.get('receipt')or {};dom=page.evaluate(LEGACY_JS)
        if type(dom['total_records'])is not int:raise ValueError('Legacy total not present')
        return dict(version=VERSION,target_path=spec['target_path'],table_visible=dom['table_visible'],
                    loading=bool(state.get('pending'))or dom['loading'],transport_error=not receipt.get('valid',False),
                    data_bound=receipt.get('valid')is True and dom['total_records']==receipt.get('total_records'),
                    total_records=dom['total_records'],displayed_records=dom['displayed_records'],
                    applied_params=receipt.get('applied_params'))
    except Exception as exc:return {'version':VERSION,'capture_error':type(exc).__name__}

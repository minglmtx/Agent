"""Private native review captures; public readiness, never an actor strategy.

Magento's review AJAX uses showLoader:false. A visible review panel/form is not
proof that its asynchronous list has mounted. Observe the original public
configuration, request completion and contentUpdated event within the same 8s
observable-ready budget. Private review counts are intentionally unavailable.
"""
from urllib.parse import parse_qs, urlsplit
import time

from .browser_page_wait import PROBE, probe_args, wait_for_observable_ready
from .io_utils import atomic_write_json
from .shopping_review_document_config import validate_review_document

BUDGET_SECONDS = 8

INSTALL = r'''publicConfig => {
 const key='__labNativeReviewReadinessV1';
 if (window[key]) return;
 const configs=[];
 for(const el of document.querySelectorAll('script[type="text/x-magento-init"]')) {
   try { const c=JSON.parse(el.textContent)?.['*']?.['Magento_Review/js/process-reviews']; if(c) configs.push(c); } catch (_) {}
 }
 const configurationSource=configs.length?'live_dom':'existing_main_frame_navigation_response';
 if(configs.length===0&&publicConfig?.configuration)configs.push(publicConfig.configuration);
 const state={configuration_source:configurationSource,configured:false,hooked:false,request_path:null,started:0,completed:0,
   mounted:0,pending:0,last_started:0,last_completed:0,last_mounted:0,last_status:null,
   last_response_empty:null,last_error:null};
 const holder={state,pending:new Map()}; window[key]=holder;
 if(configs.length!==1 || !window.jQuery || !document.querySelector('#product-review-container')) return;
 let url; try {url=new URL(configs[0].productReviewUrl,location.href);} catch(_){return;}
 if(url.origin!==location.origin || !/^https?:$/.test(url.protocol) || !url.pathname) return;
 state.configured=true;state.request_path=url.pathname;
 const matches=value=>{try{const u=new URL(value,location.href);return u.origin===url.origin&&u.pathname===url.pathname;}catch(_){return false;}};
 const $=window.jQuery;
 $(document).on('ajaxSend.labNativeReviewReadinessV1',function(_event,xhr,settings){
   if(!matches(settings.url))return;
   state.started++;state.last_started=state.started;holder.pending.set(xhr,state.started);
   state.pending=holder.pending.size;state.last_error=null;
 });
 $(document).on('ajaxComplete.labNativeReviewReadinessV1',function(_event,xhr,settings){
   if(!matches(settings.url))return;
   const seq=holder.pending.get(xhr);
   if(!seq){state.last_error='untracked_review_request_completed';return;}
   holder.pending.delete(xhr);state.pending=holder.pending.size;state.completed++;
   state.last_completed=seq;state.last_status=xhr.status;
   state.last_response_empty=typeof xhr.responseText==='string'&&xhr.responseText.trim()==='';
   if(!(xhr.status>=200&&xhr.status<300||xhr.status===304))state.last_error='native_review_request_failed';
 });
 $('#product-review-container').on('contentUpdated.labNativeReviewReadinessV1',function(){
   state.mounted++;state.last_mounted=state.last_started;
 });
 state.hooked=true;
}'''

READ = r'''() => {
 const s=window.__labNativeReviewReadinessV1?.state;
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const container=document.querySelector('#product-review-container');
 const rows=[...document.querySelectorAll('#reviews .review-item')].filter(visible);
 const current=[...new Set([...document.querySelectorAll('#reviews .pages .item.current')].filter(visible)
   .map(e=>(e.innerText.match(/\d+/g)||[])).filter(a=>a.length===1).map(a=>Number(a[0])))];
 const links=[...document.querySelectorAll('#reviews .pages a[href]')].filter(visible);
 const numbers=links.map(e=>{try{return Number(new URL(e.href,location.href).searchParams.get('p')||'1');}catch(_){return null;}});
 return {tracking:s?{...s}:null,product_id:document.querySelector('#product_addtocart_form input[name="product"]')?.value||null,
   panel_visible:visible(document.querySelector('#reviews')),container_visible:visible(container),form_visible:visible(document.querySelector('#review-form')),
   native_first_review_link:[...document.querySelectorAll('.product-info-main .reviews-actions a')]
     .some(e=>visible(e)&&e.innerText.trim()==='Be the first to review this product'),
   row_count:rows.length,rows_complete:rows.every(e=>['.review-title','.review-content'].every(sel=>!!e.querySelector(sel)?.innerText.trim())),
   pager_present:[...document.querySelectorAll('#reviews .pages')].some(visible),
   review_page:current.length===1?current[0]:null,
   other_pages:[...new Set(numbers)],pager_links_valid:numbers.every(n=>Number.isInteger(n)&&n>0)};
}'''


def review_readiness(signals, baseline, *, requested_page=None):
    """Public-only predicate; never receives expected/private record counts."""
    s=signals if isinstance(signals,dict) else {}
    t=s.get('tracking') or {};b=baseline if isinstance(baseline,dict) else {}
    numeric=lambda value:type(value)is int and value>=0
    tracked=all(numeric(t.get(k))for k in ('started','completed','mounted','pending','last_started','last_completed','last_mounted'))
    baseline_valid=all(numeric(b.get(k,0))for k in ('started','completed','mounted'))
    request_complete=(tracked and baseline_valid and t.get('configured')is True and t.get('hooked')is True
        and t['started']>b.get('started',0) and t['completed']>b.get('completed',0)
        and t['mounted']>b.get('mounted',0) and t['pending']==0
        and t['last_started']==t['last_completed']==t['last_mounted']
        and type(t.get('last_status'))is int and (200<=t['last_status']<300 or t['last_status']==304)
        and t.get('last_error')is None)
    count=s.get('row_count');current=s.get('review_page');others=s.get('other_pages')
    pager=(s.get('pager_links_valid')is True and isinstance(others,list)
        and all(type(x)is int and x>0 for x in others)
        and (s.get('pager_present')is False or type(current)is int and current>0))
    nonempty=type(count)is int and count>0 and s.get('rows_complete')is True and pager
    empty=(count==0 and type(count)is int and t.get('last_response_empty')is True
        and s.get('native_first_review_link')is True and s.get('form_visible')is True
        and s.get('pager_present')is False and not others and current is None)
    page_matches=requested_page is None or (type(requested_page)is int and requested_page>0 and current==requested_page)
    checks={'tracked_native_completion':bool(request_complete),'review_panel_visible':s.get('panel_visible')is True,
            'native_container_visible':s.get('container_visible')is True,'native_review_content_ready':bool(nonempty or empty),
            'requested_native_page_displayed':bool(page_matches)}
    return {'ready':all(checks.values()),'checks':checks,'kind':'native_empty'if empty else'native_rows'if nonempty else'pending_or_invalid'}


def _remaining(deadline):
    remaining=int((deadline-time.monotonic())*1000)
    if remaining<=0:raise TimeoutError('Native review public readiness budget exhausted')
    return remaining


def _signals(page):
    return {'review':page.evaluate(READ),'observable':page.evaluate(PROBE,probe_args('shopping'))}


def _settle(page,baseline,deadline,*,requested_page=None):
    args=probe_args('shopping')
    while True:
        _remaining(deadline);observable=page.evaluate(PROBE,args)
        if observable.get('error'):raise ValueError('Public page error during native review capture')
        if observable.get('loading'):wait_for_observable_ready(page,args,deadline)
        signals=page.evaluate(READ);judgment=review_readiness(signals,baseline,requested_page=requested_page)
        if judgment['ready']:return {'review':signals,'observable':page.evaluate(PROBE,args),'readiness':judgment}
        error=(signals.get('tracking')or{}).get('last_error')
        if error:raise ValueError(error)
        page.wait_for_timeout(min(100,_remaining(deadline)))


def _recorded_operation(page,operation,*,capture_path,action,requested_page=None,existing=False,prepare=None,public_config=None):
    """No retries: save public pre/post/timeout signals for this one operation."""
    started=time.monotonic();deadline=started+BUDGET_SECONDS
    record={'version':'native-review-public-readiness-v1','operation':operation,'budget_seconds':BUDGET_SECONDS,
            'public_signals_only':True,'private_expected_counts_used':False,'requested_page':requested_page}
    try:
        record['initial']=_signals(page)
        if prepare is not None:prepare(deadline)
        product_id=page.evaluate("() => document.querySelector('#product_addtocart_form input[name=product]')?.value||null")
        public_config=validate_review_document(public_config,page.url,product_id)
        if public_config is not None:record['public_document_configuration']=public_config
        page.evaluate(INSTALL,public_config);record['before']=_signals(page)
        track=record['before']['review'].get('tracking')or{}
        baseline={k:track.get(k,0)for k in ('started','completed','mounted')}
        # An already selected pager page reuses only a previously observed
        # completed native mount in this same document, never mere visibility.
        if existing:baseline={'started':0,'completed':0,'mounted':0}
        record['baseline']=baseline
        action(deadline)
        record['after']=_settle(page,baseline,deadline,requested_page=requested_page)
        record['status']='ready';return record
    except Exception as exc:
        record['status']='needs_diagnosis';record['diagnostic']={'type':type(exc).__name__,'message':str(exc)[:300]}
        try:record['after']=_signals(page)
        except Exception:record['post_signals_unavailable']=True
        raise
    finally:
        record['seconds']=time.monotonic()-started
        atomic_write_json(capture_path,record)


def open_review_control_ready(page,*,capture_path,public_config=None):
    """Open the native review tab during private positive controls only."""
    def prepare(deadline):
        args=probe_args('shopping');observed=page.evaluate(PROBE,args)
        if observed.get('loading'):wait_for_observable_ready(page,args,deadline)
        page.wait_for_function("() => window.jQuery&&jQuery('.product.data.items').data('mageTabs')",timeout=_remaining(deadline))
    def action(deadline):
        tab=page.locator('#tab-label-reviews a[href="#reviews"],a#tab-label-reviews[href="#reviews"]')
        if tab.count()!=1:raise ValueError('Native review tab missing or duplicated')
        if not page.locator('#reviews').is_visible():tab.click(timeout=_remaining(deadline))
    return _recorded_operation(page,'open_native_reviews',capture_path=capture_path,action=action,prepare=prepare,public_config=public_config)


def select_review_page_ready(page,number,*,capture_path):
    """Follow a visible native pager and wait for its own completed mount."""
    if type(number)is not int or number<=0:raise ValueError('Positive native page number required')
    current=page.evaluate(READ).get('review_page');existing=current==number
    def action(deadline):
        if existing:return
        candidates=[link for link in page.locator('#reviews .pages a[href]').all()
            if link.is_visible() and parse_qs(urlsplit(link.get_attribute('href')).query).get('p',['1'])==[str(number)]]
        if not candidates:raise ValueError('Native review page link missing')
        candidates[0].click(timeout=_remaining(deadline))
    return _recorded_operation(page,'select_native_review_page',capture_path=capture_path,action=action,
                               requested_page=number,existing=existing)

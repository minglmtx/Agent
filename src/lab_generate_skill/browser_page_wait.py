"""Task-independent, site-specific visible loading detection after one action.

No task goals, database checks, network-idle requirement, fixed sleeps, or action
retries. Initial site admission/readiness checks remain separate.
"""
import json
import re
import time
from functools import lru_cache
from pathlib import Path
from .gitlab_public_readiness import BLOB_SIGNALS


@lru_cache(maxsize=1)
def config():
    return json.loads((Path(__file__).resolve().parents[2]/'configs/browser-page-wait.json').read_text())


PROBE = r'''arg => {
 const selectors=Array.isArray(arg)?arg:arg.selectors;
 const gitlab=!Array.isArray(arg) && arg.domain==='gitlab';
 const shopping=!Array.isArray(arg) && arg.domain==='shopping';
 const map=!Array.isArray(arg) && arg.domain==='map';
 const error = location.protocol === 'chrome-error:';
 const visible = e => {
   if (!e.getClientRects().length) return false;
   for (let n=e; n; n=n.parentElement) {
     const s=getComputedStyle(n);
     if (s.display==='none' || s.visibility==='hidden' || s.visibility==='collapse' || Number(s.opacity)===0) return false;
   }
   return true;
 };
 const signals = error ? [] : selectors.filter(s => [...document.querySelectorAll(s)].some(visible));
 if(!error && gitlab)signals.push(...('''+BLOB_SIGNALS+r''')());
 if (!error && document.readyState==='loading') signals.push('document_loading');
 // GitLab replaces these native mount nodes when the releases Vue app starts.
 // Thereafter its visible skeleton remains until both list requests finish.
 // Do not infer loading from an empty result or from a task's expected answer.
 if (!error && gitlab && [...document.querySelectorAll('#js-releases-page,#js-show-release-page')].some(visible))
   signals.push('gitlab_release_mount_pending');
 // Directions rows can precede Leaflet's next animation-frame projection.
 // Wait only for the native route line, never for background tile downloads.
 if (!error && map && location.pathname==='/directions' &&
     [...document.querySelectorAll('#sidebar_content tr.turn')].some(visible) &&
     ![...document.querySelectorAll('.leaflet-overlay-pane path[stroke="#03f"]')].some(e=>visible(e) && (e.getAttribute('d')||'').length>20))
   signals.push('map_route_projection_pending');
 // The native OSM data loader uses jQuery AJAX without an accessible spinner.
 // Its request can still be pending after the overlay checkbox is checked.
 // Observe the site's own public request counter, never a task predicate or
 // private transport result. Tile images are not jQuery AJAX requests. The
 // existing bounded wait returns an explicit pending notice if it expires;
 // it does not confirm a warning, retry a request or declare task completion.
 if (!error && map && window.jQuery &&
     Number.isFinite(window.jQuery.active) && window.jQuery.active>0)
   signals.push('map_native_ajax_pending');
 // Storefront product panels exist before mageTabs installs their click
 // handlers. A visible review panel can then precede its listAjax response.
 // Both are public UI loading states, independent of the current task.
 if (!error && shopping) {
   // Native customer-data initialization restores cached KO sections after
   // DOMContentLoaded. A temporarily empty widget is not an empty account.
   // Observe the site's promise only: no reload, payload injection or demand
   // that disposable messages retain a data_id.
   // The server renders an unbound KO template before its public section
   // has any items. Do not wait until section.items exists to notice that
   // checkbox values and product URLs have not yet been bound.
   // Magento declares this imminent navigation in its native initializer.
   // Wait for the website's own redirect rather than issuing another action on
   // an observation about to disappear. Only a same-site declared destination
   // is recognized; arbitrary prose, expected answers and task IDs play no role.
   const scheduledRedirect=[...document.querySelectorAll('script[type="text/x-magento-init"]')].some(script=>{
     try {
       const declaration=JSON.parse(script.textContent);
       const initializer=declaration?.['*']?.['Magento_Customer/js/logout-redirect'];
       if(!initializer || typeof initializer.url!=='string' || !document.body || !visible(document.body))return false;
       const destination=new URL(initializer.url,location.href);
       return destination.origin===location.origin && destination.href!==location.href;
     } catch (_) { return false; }
   });
   // mage/apply removes initializer script nodes after parsing them. The
   // installed native module plus its still-visible logout countdown provides
   // the same public pending signal once that node is gone.
   const installedLogoutRedirect=(document.body?.classList.contains('customer-account-logoutsuccess') &&
     typeof window.require==='function' && typeof window.require.defined==='function' &&
     window.require.defined('Magento_Customer/js/logout-redirect') &&
     [...document.querySelectorAll('main p')].some(e=>visible(e) &&
       /^\s*You have signed out and will go to our homepage in [0-9]+ seconds\.\s*$/.test(e.textContent)));
   if(scheduledRedirect || installedLogoutRedirect)signals.push('shopping_native_scheduled_redirect_pending');
   const recentBlocks=[...document.querySelectorAll('.block-reorder')].filter(e=>
     /^\s*scope\s*:\s*(['"])lastOrderedItems\1\s*$/.test(e.getAttribute('data-bind')||''));
   const templatePending=recentBlocks.some(block=>[...block.querySelectorAll('#cart-sidebar-reorder > li')].some(row=>
     [...row.querySelectorAll('input[type=checkbox][name="order_items[]"]')].some(e=>e.value==='on') ||
     [...row.querySelectorAll('a.product-item-link')].some(e=>!e.getAttribute('href'))));
   const customerModule='Magento_Customer/js/customer-data';
   if (typeof window.require==='function' && typeof window.require.defined==='function' && window.require.defined(customerModule)) {
     const data=window.require(customerModule);
     if (data.getInitCustomerData().state()==='pending')
       signals.push('shopping_customer_data_initialization_pending');
     // The native promise resolves before Magento_Ui/KO necessarily binds the
     // recently ordered widget. Compare its public rows with its own public
     // section, never with a task's private expected products. Do not load an
     // AMD module or require an absent/static/empty component to become ready.
     if (recentBlocks.length && typeof data.get==='function') {
       const section=data.get('last-ordered-items')();
       const items=section && section.items;
       if(templatePending && (items===undefined || items===null))
         signals.push('shopping_recent_items_binding_pending');
       const text=s=>typeof s==='string'?s.replace(/\s+/g,' ').trim():null;
       const id=v=>typeof v==='number' && Number.isSafeInteger(v) && v>0?String(v):
         typeof v==='string' && /^[1-9][0-9]*$/.test(v)?v:null;
       const path=v=>{
         if (typeof v!=='string') return null;
         try {
           const u=new URL(v,location.href);
           return u.origin===location.origin?u.pathname+u.search+u.hash:null;
         } catch (_) { return null; }
       };
       // Invalid section types remain capture errors for the completion
       // checker, rather than an invented loading state or an empty success.
       const identities=Array.isArray(items)?items.map(e=>e && typeof e==='object'?
         [id(e.id),text(e.name),path(e.url)]:[null,null,null]):null;
       if (identities && identities.length && identities.every(e=>e.every(v=>v!==null && v!==''))) {
         const wanted=identities.map(e=>JSON.stringify(e)).sort();
         const bound=recentBlocks.some(block=>{
           const rows=[...block.querySelectorAll('#cart-sidebar-reorder > li')];
           if (rows.length!==wanted.length) return false;
           const actual=rows.map(row=>{
             const fields=[...row.querySelectorAll('input[type=checkbox][name="order_items[]"]')];
             const links=[...row.querySelectorAll('a.product-item-link[href]')];
             if (fields.length!==1 || links.length!==1) return null;
             const values=[id(fields[0].value),text(links[0].textContent),path(links[0].href)];
             return values.every(v=>v!==null && v!=='')?JSON.stringify(values):null;
           });
           return actual.every(v=>v!==null) && actual.sort().every((v,i)=>v===wanted[i]);
         });
         if (!bound) signals.push('shopping_recent_items_binding_pending');
       }
     }
   } else if ([...document.querySelectorAll('script[type="text/x-magento-init"]')].some(e=>e.textContent.includes(customerModule))) {
     signals.push('shopping_customer_data_initializer_pending');
   }
   if(templatePending && !(typeof window.require==='function' && typeof window.require.defined==='function' && window.require.defined(customerModule)))
     signals.push('shopping_recent_items_binding_pending');
   const productTabs=document.querySelector('.product.data.items');
   if (productTabs && visible(productTabs) && !(window.jQuery && jQuery(productTabs).data('mageTabs')))
     signals.push('shopping_product_tabs_pending');
   // A theme's "active" class can coexist with aria-expanded=false. A
   // collapsed panel is not loading and must remain an actor decision.
   const nativeReviewObserver=window.__labPublicReviewObserverV1;
   if(nativeReviewObserver?.version==='shopping-public-review-observer-v1' && typeof nativeReviewObserver.signals==='function')
     signals.push(...nativeReviewObserver.signals());
   const reviews=document.querySelector('#reviews');
   const count=document.querySelector('#tab-label-reviews-title')?.innerText.match(/[0-9][0-9,]*/);
   if (reviews && visible(reviews) && !window.__labNativeReviewReadinessV1?.state?.last_error && count && Number(count[0].replace(/,/g,''))>0 &&
       ![...reviews.querySelectorAll('.review-item')].some(visible)) signals.push('shopping_review_rows_pending');
 }
 // Native project Issues first renders an empty placeholder before starting
 // its GraphQL requests. Missing public tab counters are a concrete pending
 // signal even before a spinner appears. Genuine empty-project onboarding
 // has no counters and must not wait for nonexistent issues.
 if (!error && gitlab && /\/-\/issues\/?$/.test(location.pathname)) {
   const counters=[...document.querySelectorAll('[data-qa-selector="opened_issuables_tab"],[data-qa-selector="closed_issuables_tab"],[data-qa-selector="all_issuables_tab"]')].filter(visible);
   const text=e=>(e.closest('a')||e).innerText;
   if (counters.length && counters.some(e=>!/[0-9]/.test(text(e)))) signals.push('gitlab_issue_counters_pending');
   const active=counters.find(e=>e.closest('a')?.classList.contains('active'));
   const count=active?text(active).match(/[0-9][0-9,]*/):null;
   const items=[...document.querySelectorAll('[data-qa-selector="issuable_title_link"]')].filter(visible);
   if (count && Number(count[0].replace(/,/g,''))>0 && !items.length) signals.push('gitlab_issue_rows_pending');
 }
 // Project home can remove its spinner before Vue inserts the file rows.
 // A rendered native commit identifies a populated repository; empty-project
 // onboarding has no commit and must not wait for nonexistent file entries.
 // Vue repository navigation can retain the home body's data-page on blob
 // and commit views. Those pages have no directory rows to wait for.
 if (!error && gitlab && !location.pathname.includes('/-/') && document.body.getAttribute('data-page')==='projects:show' &&
     [...document.querySelectorAll('a[href*="/-/commit/"]')].some(visible) &&
     ![...document.querySelectorAll('.tree-item a[href*="/-/tree/"],.tree-item a[href*="/-/blob/"]')].some(visible))
   signals.push('gitlab_repository_rows_pending');
 return {url:location.href,error,signals,loading:signals.length>0};
}'''
READY = 'arg => { const s = ('+PROBE+')(arg); return s.error || !s.loading; }'


def snapshot_has_loader(obs):
    """An explicit AX loading widget, not arbitrary webpage prose mentioning it."""
    return bool(re.search(r"^\s*(?:\[[^\]\n]+\]\s*)?(?:image|progressbar|status) '(?:Loading(?:\.\.\.|…)?|Please wait(?:\.\.\.|…)?)'(?:,.*)?$",
                          obs.get('axtree_txt',''), re.M | re.I))


def probe_args(domain):
    cfg=config();return {'domain':domain,'selectors':list(dict.fromkeys(cfg['common_selectors']+cfg['sites'][domain]['selectors']))}


def wait_for_observable_ready(page,args,deadline):
    """Cover a reappearing visible loader within one shared absolute deadline."""
    from playwright.sync_api import TimeoutError
    while True:
        remaining=int((deadline-time.monotonic())*1000)
        if remaining<=0:raise TimeoutError('Visible loading capture budget exhausted')
        page.wait_for_function(READY,arg=args,timeout=remaining,polling=100)
        state=page.evaluate(PROBE,args)
        if state['error'] or not state['loading']:return state


def settle_gitlab_capture(page,timeout_ms=8000):
    """CPU reference captures use exactly the actor's observable loading signals."""
    start=time.monotonic();args=probe_args('gitlab');initial=state=page.evaluate(PROBE,args)
    if state['loading']:state=wait_for_observable_ready(page,args,start+timeout_ms/1000)
    return {'initial':initial,'final':state,'seconds':time.monotonic()-start,'browser_actions_added':0}


def refresh_on_loading(env, observation_fn, obs, *, domain, timeout_ms=None):
    from playwright.sync_api import TimeoutError as PWTimeout, Error as PWError
    cfg=config();profile=cfg['sites'][domain];budget=profile['max_wait_ms'] if timeout_ms is None else timeout_ms
    if not 0 < budget <= 60000:raise ValueError('Page wait budget must be 1..60000 ms')
    # Old diagnostic runners may still call a refresh helper after the shared
    # step. One action receives only one loading wait, never duplicate budgets.
    prior=obs.get('page_wait',{})
    if prior.get('policy')==cfg['version'] and prior.get('domain')==domain:return obs
    raw=getattr(env,'unwrapped',env);page=raw.page;start=time.monotonic()
    from .browser_health import require_live_page
    require_live_page(page)
    if domain=='shopping':
        from .shopping_public_review_observer import prepare_public_review_observer
        prepare_public_review_observer(page)
    selectors=probe_args(domain)
    transition=False
    try:initial=page.evaluate(PROBE,selectors)
    except PWError as exc:
        if not any(t in str(exc).lower() for t in ('execution context was destroyed','frame was detached','cannot find context with specified id')):raise
        # A navigation destroyed the old DOM context: a concrete loading signal.
        transition=True
        initial={'url':page.url,'error':False,'loading':True,'signals':['navigation_transition']}

    status='browser_error' if initial['error'] else 'not_loading'
    refreshed=False
    refresh_reason=None
    if initial['loading']:
        try:
            if transition:
                page.wait_for_load_state('domcontentloaded',timeout=budget)
            wait_for_observable_ready(page,selectors,start+budget/1000)
            status='browser_error' if page.url.startswith('chrome-error:') else 'settled'
        except PWTimeout:status='wait_budget_exhausted'
        # Mandatory fresh capture after waiting. Capture errors propagate; do
        # not hide a dead browser by returning the previous observation.
        current=observation_fn(raw._get_obs());refreshed=True
    elif initial['url']!=obs.get('url'):
        current=observation_fn(raw._get_obs());refreshed=True
    elif snapshot_has_loader(obs) and not initial['error']:
        # AX can capture a loading widget just before it disappears. The later
        # DOM probe sees no loader, but returning that earlier AX would expose
        # an empty transitional page to the actor. Recapture once, with no wait,
        # action retry, evaluator reference, or task-specific correction.
        current=observation_fn(raw._get_obs());refreshed=True;status='settled';refresh_reason='snapshot_loading_resolved'
    else:current=dict(obs)
    polling_status=status
    final_loading_probe=None
    # AX capture can outlive the polling deadline while the native navigation
    # finishes. Report what the returned observation actually shows, rather than
    # carry an expired loading signal into a completed page. This probe never
    # waits, retries an action, or extends the original waiting budget.
    if refreshed and status=='wait_budget_exhausted':
        try:final_loading_probe=page.evaluate(PROBE,selectors)
        except PWError as exc:
            if not any(t in str(exc).lower() for t in ('execution context was destroyed','frame was detached','cannot find context with specified id')):raise
            final_loading_probe={'url':page.url,'error':False,'loading':True,'signals':['navigation_transition']}
        if final_loading_probe['error']:
            status='browser_error'
        elif (final_loading_probe['url']==current.get('url')
              and not final_loading_probe['loading']
              and not snapshot_has_loader(current)):
            status='settled';refresh_reason='loading_resolved_during_capture'
    current['last_action_error']=obs.get('last_action_error','')
    current['action_execution_error']=current['last_action_error']
    if status=='browser_error':
        note='Page observation: the browser is displaying an error document, not usable website content.'
    elif status=='wait_budget_exhausted':
        from .native_control_observation import LOADING_WARNING
        note=LOADING_WARNING
    else:note=''
    current['page_observation_warning']=note
    if note:current['last_action_error']='\n'.join(filter(None,[current['last_action_error'],note]))
    from .browser_request_policy import consume_navigation_block
    if getattr(page,'context',None) is not None:
        blocked=consume_navigation_block(page)
        if blocked:
            current['network_feedback']=blocked
            current['last_action_error']='\n'.join(filter(None,[current['last_action_error'],
                'Navigation to '+blocked['blocked_origin']+' was blocked because this environment only allows its declared local website services. The external page was not loaded.']))
    if domain=='shopping':
        from .shopping_public_review_observer import public_review_observer_status
        component=public_review_observer_status(page)
        if component and component.get('last_error'):
            current['last_action_error']='\n'.join(filter(None,[current['last_action_error'],
                'Page observation: the native Reviews component reported '+component['last_error']+'. Current review content may be incomplete.']))
    current['page_wait']={'policy':cfg['version'],'domain':domain,'status':status,
        'observed_signals':initial['signals'],'timeout_ms':budget,'seconds':time.monotonic()-start,
        'observation_refreshed':refreshed,'browser_actions_added':0,
        **({'refresh_reason':refresh_reason} if refresh_reason else {}),
        **({'polling_status':polling_status,
            'final_loading_probe':final_loading_probe} if final_loading_probe is not None else {})}
    return current

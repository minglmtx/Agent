"""Public native Review observer for every Shopping page, not a task strategy.

Reads only existing main-document responses. Installs the existing native
request/mount tracker before actor actions, exposes observable pending signals,
and releases per-document hooks on navigation/close. No GET, goto, click, private
review count, request retry, or task/evaluator data is accepted.
"""
import hashlib
import weakref
from urllib.parse import urldefrag

from .shopping_review_document_config import parse_review_document, validate_review_document, _document_url

def _is_context_transition(exc):
    return any(t in str(exc).lower() for t in ('execution context was destroyed','frame was detached','cannot find context with specified id'))


VERSION = 'shopping-public-review-observer-v1'
KEY = '__labPublicReviewObserverV1'
_CONTEXTS = weakref.WeakKeyDictionary()

# Only call a hook installed by this observer. The existing shared PROBE can
# embed this optional call without importing shopping_review_readiness back
# into browser_page_wait (which would create a Python import cycle).
PUBLIC_SIGNALS = r'''() => {
 const observer=window.__labPublicReviewObserverV1;
 return observer && observer.version==='shopping-public-review-observer-v1' &&
   typeof observer.signals==='function' ? observer.signals() : [];
}'''

DISPOSE = r'''() => {
 const observer=window.__labPublicReviewObserverV1;
 if(observer && typeof observer.dispose==='function')observer.dispose();
}'''


def _arm_script():
    # Reuse the installed reader and tracker verbatim. These imports are lazy:
    # shopping_review_readiness imports browser_page_wait's public primitives.
    from .shopping_review_readiness import INSTALL, READ
    return r'''arg => {
 const key='__labPublicReviewObserverV1', trackerKey='__labNativeReviewReadinessV1';
 const old=window[key];
 if(old && old.identity===arg.identity && old.version===arg.version) {
   old.prepare(); return old.status();
 }
 if(old && typeof old.dispose==='function')old.dispose();
 const nativeInstall=(''' + INSTALL + r'''), readNative=(''' + READ + r''');
 const visible=e=>{if(!e||!e.getClientRects().length)return false;
   for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);
     if(s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse'||Number(s.opacity)===0)return false;}
   return true;};
 let timer=null,observer=null,disposed=false,lastError=null;
 const publicState={version:arg.version,identity:arg.identity,phase:'not_configured',
   public_signals_only:true,extra_http_requests:0,browser_actions_added:0};
 const removeTracker=()=>{
   const holder=window[trackerKey];
   if(holder?.state?.hooked && window.jQuery) {
     jQuery(document).off('.labNativeReviewReadinessV1');
     jQuery('#product-review-container').off('.labNativeReviewReadinessV1');
   }
   delete window[trackerKey];
 };
 const stopBoot=()=>{
   if(timer!==null){clearInterval(timer);timer=null;}
   if(observer!==null){observer.disconnect();observer=null;}
   document.removeEventListener('DOMContentLoaded',prepare);
 };
 const productMatches=()=>{
   const id=document.querySelector('#product_addtocart_form input[name="product"]')?.value;
   if(!id||!document.querySelector('#product-review-container'))return false;
   if(arg.publicConfig && (id!==arg.publicConfig.public_product_id||
       location.href.split('#')[0]!==arg.publicConfig.document_url))return false;
   return true;
 };
 function prepare(){
   if(disposed)return;
   if(!productMatches()){publicState.phase='not_product';stopBoot();return;}
   const holder=window[trackerKey];
   // An early private INSTALL can leave a dead holder. Never keep it forever,
   // even when jQuery never arrives, or duplicate already-configured hooks.
   if(holder && holder.state?.hooked!==true)removeTracker();
   if(!window.jQuery){publicState.phase='awaiting_native_jquery';return;}
   try{nativeInstall(arg.publicConfig);}catch(_){lastError='native_tracker_install_failed';publicState.phase='unavailable';stopBoot();return;}
   const state=window[trackerKey]?.state;
   if(state?.configured===true&&state?.hooked===true){publicState.phase='observing_native_reviews';stopBoot();}
   else{removeTracker();publicState.phase='configuration_unavailable';stopBoot();}
 }
 function signals(){
   if(disposed)return [];
   prepare();
   if(!visible(document.querySelector('#reviews'))||!visible(document.querySelector('#product-review-container')))return [];
   const s=readNative(),t=s.tracking;
   if(s.panel_visible!==true||s.container_visible!==true||
       t?.configured!==true||t?.hooked!==true)return [];
   // HTTP failures/untracked events are diagnostics, never invented long waits.
   if(t.last_error)return [];
   const numbers=['started','completed','mounted','pending','last_started','last_completed','last_mounted'];
   if(!numbers.every(k=>Number.isInteger(t[k])&&t[k]>=0))return [];
   if(t.pending>0)return ['shopping_native_review_request_pending'];
   if(t.started>0 && (t.last_completed<t.last_started||t.last_mounted<t.last_started))
     return ['shopping_native_review_mount_pending'];
   return [];
 }
 function status(){return {...publicState,boot_timer_active:timer!==null,
   last_error:lastError||(window[trackerKey]?.state?.last_error)||null};}
 function dispose(){
   if(disposed)return;disposed=true;stopBoot();removeTracker();
   if(window[key]===api)delete window[key];
 }
 const api={version:arg.version,identity:arg.identity,prepare,signals,status,dispose};
 window[key]=api;prepare();
 if(publicState.phase==='awaiting_native_jquery') {
   const deadline=performance.now()+arg.bootstrapMs;
   timer=setInterval(()=>{
     prepare();if(performance.now()>=deadline){stopBoot();if(publicState.phase==='awaiting_native_jquery')publicState.phase='native_jquery_unavailable';}
   },50);
   observer=new MutationObserver(()=>prepare());observer.observe(document,{childList:true,subtree:true});
   document.addEventListener('DOMContentLoaded',prepare);
 }
 return status();
}'''


class PageReviewObserver:
    def __init__(self, page, *, bootstrap_ms=8000):
        self._page = weakref.ref(page)
        self.bootstrap_ms = bootstrap_ms
        self.current_request = None
        self.public_config = None
        self.navigation_sequence = 0
        self.closed = False
        self.config_status = 'no_existing_document_response'
        self.observed_mounts = []
        self._observed_mount_keys = set()
        self._callbacks = {'request': self._request, 'requestfinished': self._finished,
                           'close': self._closed}
        for event, callback in self._callbacks.items():
            page.on(event, callback)

    def _is_document(self, request):
        page = self._page()
        try:
            return page is not None and request.resource_type == 'document' and request.frame == page.main_frame
        except Exception:
            return False

    def _request(self, request):
        if not self._is_document(request):
            return
        self.current_request = request
        self.public_config = None
        self.navigation_sequence += 1
        self.config_status = 'existing_document_response_pending'

    def _finished(self, request):
        if self.closed or not self._is_document(request):
            return
        # The first native document request may precede the context Page event.
        # A completed main-frame response is still its actual first transport;
        # adopt it only for a never-observed initial page, never a later stale
        # response or same-URL refresh with an existing document sequence.
        if self.current_request is None and self.navigation_sequence==0:
            self.current_request=request;self.navigation_sequence=1
        if request is not self.current_request:
            return
        try:
            response = request.response()
            if response is None or response.status != 200:
                self.config_status = 'native_document_not_http200'
                return
            content_type = response.headers.get('content-type', '').split(';', 1)[0].strip().lower()
            if content_type not in ('text/html', 'application/xhtml+xml'):
                self.config_status = 'not_native_product_html'
                return
            # This reads already-completed transport bytes, never page.request.
            self.public_config = parse_review_document(response.text(), response.url)
            self.config_status = 'safe_public_configuration_captured'
        except (ValueError, TypeError):
            self.config_status = 'not_unambiguous_native_product_document'
        except Exception:
            self.config_status = 'existing_document_configuration_unavailable'
        # Drop request/response handles; cache only the validated safe fields.
        finally:
            self.current_request = None

    def prepare(self):
        page = self._page()
        if self.closed or page is None or page.is_closed():
            return {'version': VERSION, 'phase': 'closed'}
        public_url = urldefrag(page.url)[0]
        try:_document_url(public_url)
        except ValueError:
            page.evaluate(DISPOSE)
            return {'version':VERSION,'phase':'unsafe_document_url_not_observed'}
        product_id = page.evaluate("() => document.querySelector('#product_addtocart_form input[name=product]')?.value||null")
        config = self.public_config
        if config is not None:
            try:
                validate_review_document(config, public_url, product_id)
            except ValueError:
                config = None
        identity = str(self.navigation_sequence) + ':' + hashlib.sha256(public_url.encode()).hexdigest() + ':' + str(product_id)
        return page.evaluate(_arm_script(), {'version': VERSION, 'identity': identity,
                                           'publicConfig': config, 'bootstrapMs': self.bootstrap_ms})

    def record_observed_mount(self):
        """Only a real completed, visible mount; never fill unvisited pages."""
        page=self._page()
        if self.closed or page is None or page.is_closed():return None
        from .shopping_review_readiness import READ, review_readiness
        signals=page.evaluate(READ)
        if review_readiness(signals,{})['ready']is not True:return None
        tracking=signals['tracking']
        key=(self.navigation_sequence,signals['product_id'],tracking['last_mounted'],signals['review_page'])
        if key in self._observed_mount_keys:return None
        from .shopping_remaining_normal import read_reviews
        state=read_reviews(page)
        try:_document_url(urldefrag(page.url)[0])
        except ValueError:return None
        record={'version':VERSION,'document_sequence':self.navigation_sequence,
            'document_url':urldefrag(page.url)[0],'native_mount_sequence':tracking['last_mounted'],
            'native_page':signals['review_page'],'state':state,'public_observed_only':True,
            'unvisited_pages_filled':False,'private_expected_counts_used':False}
        self.observed_mounts.append(record);self._observed_mount_keys.add(key)
        return record

    def signals(self):
        page = self._page()
        if self.closed or page is None or page.is_closed():
            return []
        return page.evaluate(PUBLIC_SIGNALS)

    def metadata(self):
        # No request/response, body, form key or private/evaluator fields.
        return {'version': VERSION, 'navigation_sequence': self.navigation_sequence,
                'configuration_status': self.config_status, 'public_configuration': self.public_config,
                'extra_http_requests': 0, 'browser_actions_added': 0, 'closed': self.closed,
                'observed_native_mounts':list(self.observed_mounts)}

    def _closed(self, *_):
        self.close(dom_cleanup=False)

    def close(self, *, dom_cleanup=True):
        if self.closed:
            return
        page = self._page()
        self.closed = True
        if page is not None:
            if dom_cleanup and not page.is_closed():
                try:
                    page.evaluate(DISPOSE)
                except Exception:
                    pass
            for event, callback in self._callbacks.items():
                try:
                    page.remove_listener(event, callback)
                except Exception:
                    pass
        self.current_request = None
        self.public_config = None
        self.observed_mounts.clear();self._observed_mount_keys.clear()


class ShoppingPublicReviewObserver:
    """Context lifetime; one public cache/tracker per native page/document."""
    def __init__(self, context, *, bootstrap_ms=8000):
        if type(bootstrap_ms) is not int or not 1 <= bootstrap_ms <= 8000:
            raise ValueError('Bounded public bootstrap budget required')
        self._context = weakref.ref(context)
        self.bootstrap_ms = bootstrap_ms
        self.pages = weakref.WeakKeyDictionary()
        self.closed = False
        self._page_callback = self.attach
        self._close_callback = lambda *_: self.close()
        context.on('page', self._page_callback)
        context.on('close', self._close_callback)
        for page in context.pages:
            self.attach(page)
        _CONTEXTS[context] = self

    def attach(self, page):
        if not self.closed and page not in self.pages:
            self.pages[page] = PageReviewObserver(page, bootstrap_ms=self.bootstrap_ms)
        return self.pages.get(page)

    def prepare(self, page):
        state = self.attach(page)
        if state is None:return {'version':VERSION,'phase':'closed'}
        from playwright.sync_api import Error
        try:return state.prepare()
        except Error as exc:
            if not _is_context_transition(exc):raise
            return {'version':VERSION,'phase':'navigation_context_transition'}

    def record(self,page):
        state=self.attach(page)
        return state.record_observed_mount()if state is not None else None

    def timeline(self):
        return [entry for state in self.pages.values()for entry in state.observed_mounts]

    def close(self):
        if self.closed:
            return
        self.closed = True
        context = self._context()
        for state in list(self.pages.values()):
            state.close()
        self.pages.clear()
        if context is not None:
            for event, callback in [('page', self._page_callback), ('close', self._close_callback)]:
                try:
                    context.remove_listener(event, callback)
                except Exception:
                    pass
            if _CONTEXTS.get(context) is self:
                del _CONTEXTS[context]


def _public_observer(page):
    """Only a context already explicitly registered by Shopping can opt in."""
    context = getattr(page, 'context', None)
    if context is None:
        return None
    try:
        return _CONTEXTS.get(context)
    except TypeError:
        # A legacy facade sentinel cannot have been registered as a context.
        return None


def prepare_public_review_observer(page):
    """Unattached/legacy facades add no work; real browser errors propagate."""
    observer = _public_observer(page)
    return observer.prepare(page) if observer is not None else None


def public_review_observer_status(page):
    """Read optional public diagnostics only for an explicitly attached context.

    Do not create hooks or evaluate another script on an ordinary legacy page.
    Browser errors from the property lookup or an attached page stay visible.
    """
    if _public_observer(page) is None:
        return None
    return page.evaluate('() => window.' + KEY + '?.status?.() || null')

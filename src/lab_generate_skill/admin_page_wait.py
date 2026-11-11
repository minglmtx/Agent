"""Bounded observation refresh for Magento's visible loading overlays.

No browser actions, clicks, database access, or task-success oracle. This adapter
uses BrowserGym's installed _get_obs API, covered by CPU/online integration checks.
"""
import time

VISIBLE_LOADING = '''() => [...document.querySelectorAll('[data-role="spinner"], .loading-mask')].some(e => {
 const s=getComputedStyle(e);return e.getClientRects().length>0 && s.display!=='none' && s.visibility!=='hidden';
})'''


def refresh_after_loading(env, observation_fn, obs, *, timeout_ms=None):
    from .browser_page_wait import refresh_on_loading
    return refresh_on_loading(env,observation_fn,obs,domain='shopping_admin',timeout_ms=timeout_ms)


ADMIN_READY = r"""() => {
 const visible=e=>e.getClientRects().length>0 && getComputedStyle(e).visibility!=='hidden';
 if(document.readyState==='loading') return false;
 if([...document.querySelectorAll('[data-role="spinner"],.loading-mask')].some(visible)) return false;
 if(window.jQuery && window.jQuery.active>0) return false;
 const path=location.pathname.replace(/\/key\/[^/]+\/?$/, '/');
 if(/\/(?:catalog\/product|customer\/(?:index|group)|sales\/(?:order|shipment|creditmemo)|search\/term|cms\/(?:page|block))\/(?:index\/?)?$/.test(path)) {
   return !!document.querySelector('table.data-grid tbody tr,table.data tbody tr');
 }
 return !!document.querySelector('h1');
}"""


def settle_admin_page(page, *, timeout_ms=60000, allow_browser_error=False):
    """Wait for rendered grid or empty-state row, not just an early h1 shell."""
    start=time.monotonic()
    condition=ADMIN_READY
    if allow_browser_error:
        condition="() => location.protocol==='chrome-error:' || ("+ADMIN_READY+")()"
    page.wait_for_function(condition,timeout=timeout_ms)
    status='browser_error' if allow_browser_error and page.url.startswith('chrome-error:') else 'settled'
    return {'status':status,'seconds':time.monotonic()-start,'timeout_ms':timeout_ms,
            'policy':'admin-rendered-grid-v2','browser_actions_added':0}

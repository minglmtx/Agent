"""Optional native Map navigation setup and observation, never actor actions.

The unchanged original start is opened by the shared runner. Only declared
local account/editor setup is performed before its disposable baseline; public
terminal state is read before the common page snapshot, without moving the map.
"""
from urllib.parse import urlsplit

from . import map_editor_navigation as editor
from . import map_native_navigation as native
from .map_community_fixture import profile_for_contracts as community_profile
from .map_native_account_bootstrap import initialize_native_account
from .map_view import wait_native_view
from .map_local_capabilities import geo_triplet, same_center
from .io_utils import atomic_write_json


def family(contract):
    completion=contract.get('completion',{})
    enabled=[key for key in ('map_editor','map_native_navigation') if completion.get(key)]
    if len(enabled)>1 or (enabled and contract.get('domain')!='map'):
        raise ValueError('One native navigation family per Map task is required')
    return enabled[0] if enabled else None


def profile_for_contracts(rows,domain):
    editor_profile=editor.profile_for_contracts(rows,domain)
    families=[family(row)for row in rows]
    if any(key=='map_native_navigation' for key in families):
        if domain!='map' or any(key!='map_native_navigation' for key in families):
            raise ValueError('Native Map navigation requires a dedicated manifest')
        if community_profile(rows,domain) is None:
            raise ValueError('Native navigation requires declared local account provenance')
        for row in rows:native.validate(row['completion']['map_native_navigation'])
    return editor_profile



def initialize_actor_account(site):
    """Borrow the retained actor manager; own only this disposable browser.

    BrowserGym keeps its sync Playwright manager after closing an episode.
    Account bootstrap must use that manager when profiles share one process.
    The standalone CPU controls still pass their own browser to the original
    initialize_native_account function.
    """
    from browsergym.core import _get_global_playwright
    browser=_get_global_playwright().chromium.launch(headless=True)
    try:
        return initialize_native_account(site,browser=browser)
    finally:
        browser.close()


def prepare_site(site,contract,editor_profile,directory):
    kind=family(contract)
    if kind=='map_editor':
        # The editor uses the same native account bootstrap as navigation.
        # BrowserGym can already own a live sync manager from a prior episode.
        from browsergym.core import _get_global_playwright
        browser=_get_global_playwright().chromium.launch(headless=True)
        try:
            proof=editor.prepare_site(site,editor_profile,browser=browser)
        finally:
            browser.close()
        atomic_write_json(directory/'native-map-initialization.json',proof)
    elif kind=='map_native_navigation':
        native.verify_reference(contract)
        existing=getattr(site,'_native_navigation_account_baseline',None)
        if existing is None:
            proof=initialize_actor_account(site)
            site._native_navigation_account_baseline=proof
        else:
            site.reset_guard.require_unchanged()
            proof=dict(existing,verified_clean_reuse=True)
        atomic_write_json(directory/'native-map-initialization.json',proof)


def authenticate_if_required(page,site,contract):
    kind=family(contract)
    if kind:page.context.set_extra_http_headers({'Accept-Language':'en-US'})
    if kind=='map_editor' or (kind=='map_native_navigation' and
            contract['completion'][kind]['kind']=='upload_form'):
        editor.authenticate(page,site)


def observe_initial(page,contract,directory):
    kind=family(contract)
    if kind=='map_editor':
        state=editor.observe_initial(page,contract)
        atomic_write_json(directory/'initial-map-editor-view.json',state)
    elif kind=='map_native_navigation':
        native.verify_reference(contract)
        view=None
        if urlsplit(contract['start_path']).path in ('/','/directions','/search'):
            view=wait_native_view(page,contract['start_path'])
        expected=contract['completion'][kind]['initial_area']
        if expected is not None and not same_center(expected,geo_triplet(view)):
            raise RuntimeError('Original initial area differs from independent native references')
        atomic_write_json(directory/'initial-map-native-view.json',{
            'original_start_path':contract['start_path'],'native_view':view,
            'initial_area_verified':expected is None or view is not None})


def read_terminal(page,contract):
    kind=family(contract)
    if kind=='map_editor':return {kind:editor.read_terminal(page)}
    if kind=='map_native_navigation':return {kind:native.read_terminal(page)}
    return {}

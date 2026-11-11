"""Explicit native Map locale initialization before a disposable baseline.

First native authentication writes Accept-Language to User#languages. Verify
that exact native write, not an arbitrary user change, before rebasing once.
No account credentials, raw account rows, OAuth DOM or tokens are returned.
"""
import json
import re
from urllib.parse import urlsplit

from .browser_request_policy import install_local_network_policy
from .io_utils import atomic_write_json
from .map_community_fixture import VERSION as FIXTURE_VERSION, USERNAME, PASSWORD, records
from .map_reset_guard import STATE_SQL, checked_state, persistent_files

VERSION='native-map-account-locale-v1'


def account_locale_state(site):
    row=json.loads(site.app_sql("""SELECT json_build_object(
      'languages', (SELECT languages FROM users WHERE display_name='LocalBenchmarkMapper'),
      'non_language_row_hash', (SELECT md5((to_jsonb(u)-'languages')::text)
                               FROM users u WHERE display_name='LocalBenchmarkMapper'));"""))
    raw=row['languages']
    if raw is not None and not isinstance(raw,str):
        raise ValueError('Native serialized account language is malformed')
    row['languages']=re.split(r' *[, ] *',raw) if raw else []
    return row


def initialize_native_account(site, *, browser=None):
    """Use native login once; allow only verified deterministic locale setup."""
    if getattr(site,'community_fixture',None)!=FIXTURE_VERSION or not getattr(site,'reset_guard',None):
        raise ValueError('Declared tracked disposable Map account required')
    if browser is None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            owned=pw.chromium.launch(headless=True)
            try:
                return initialize_native_account(site,browser=owned)
            finally:
                owned.close()
    before=account_locale_state(site)
    guard_before=checked_state(json.loads(site.app_sql(STATE_SQL)))
    files_before=persistent_files(site.state/'frontend/app')
    records_before=records(site)
    if guard_before['changed'] or before['languages'] not in ([],['en-US']):
        raise RuntimeError('Fresh account/guard locale baseline differs from declared profile')
    ctx=browser.new_context(viewport={'width':1280,'height':720},locale='en-US',
                            extra_http_headers={'Accept-Language':'en-US'})
    try:
        install_local_network_policy(ctx,site.allowed_netlocs)
        page=ctx.new_page();page.set_default_timeout(15000)
        response=page.goto(site.url+'/login',wait_until='domcontentloaded',timeout=30000)
        if response is None or response.status!=200:
            raise RuntimeError('Native local account login unavailable')
        page.locator('#login_form input[name=username]').fill(USERNAME)
        page.locator('#login_form input[name=password]').fill(PASSWORD)
        page.locator('#login_form input[type=submit],#login_form button[type=submit]').click(timeout=15000)
        page.wait_for_url(lambda value:urlsplit(str(value)).path!='/login',timeout=30000)
        page.wait_for_function("() => !!document.querySelector('a[href*=LocalBenchmarkMapper]')",timeout=30000)
    finally:
        ctx.close()
    after=account_locale_state(site)
    state=checked_state(json.loads(site.app_sql(STATE_SQL)))
    expected=['public.users'] if before['languages']==[] else []
    proof={'version':VERSION,'native_controller':'ApplicationController#set_locale',
      'browser_accept_language':'en-US','initial_languages':before['languages'],
      'native_initialized_languages':after['languages'],'changed_tables':state['changed'],
      'expected_changed_tables':expected,
      'non_language_account_columns_unchanged':after['non_language_row_hash']==before['non_language_row_hash'],
      'sequences_unchanged':state['sequences']==guard_before['sequences'],
      'persistent_files_unchanged':persistent_files(site.state/'frontend/app')==files_before,
      'synthetic_records_unchanged':records(site)==records_before,
      'synthetic_account':True,'original_benchmark_equivalence':False}
    atomic_write_json(site.logs/'native-account-initialization-observation.json',proof)
    if (after['languages']!=['en-US'] or state['changed']!=expected or
        not all(proof[k] for k in ('non_language_account_columns_unchanged','sequences_unchanged',
                                  'persistent_files_unchanged','synthetic_records_unchanged'))):
        raise RuntimeError('Native login initialization changed more than declared account language')
    site.app_sql('TRUNCATE codex_reset_guard.changed;')
    site.reset_guard.initial=site.reset_guard.fingerprint()
    proof['all_subsequent_writes_tracked']=True
    return proof

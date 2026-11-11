"""Benchmark UI authentication shared by Playwright and BrowserGym sessions."""
import ast
from urllib.parse import urlsplit


def credentials(root,domain):
    tree=ast.parse((root/'paper_repos/WebArena/browser_env/env_config.py').read_text())
    for n in tree.body:
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ACCOUNTS' for t in n.targets):return ast.literal_eval(n.value)[domain]
    raise RuntimeError('No benchmark account binding')


def _login(page,site,auth,*,wait_for_customer_data=False):
    if site.domain=='gitlab':
        page.goto(site.url+'/users/sign_in',wait_until='domcontentloaded',timeout=60000)
        # BrowserGym globally changes Playwright get_by_test_id to use bid.
        # Data-testid selectors remain tied to the actual site markup.
        page.locator('[data-testid="username-field"]').fill(auth['username'])
        page.locator('[data-testid="password-field"]').fill(auth['password'])
        page.locator('[data-testid="sign-in-button"]').click()
        page.wait_for_url(lambda u:'/users/sign_in' not in str(u),timeout=60000,wait_until='domcontentloaded')
    elif site.domain=='shopping':
        page.goto(site.url+'/customer/account/login/',wait_until='load',timeout=60000)
        # Magento synchronizes the rendered form token from its form_key cookie.
        # Do not submit before client initialization has made them agree.
        page.wait_for_function(SHOPPING_FORM_READY,timeout=15000)
        if wait_for_customer_data:wait_shopping_customer_data(page)
        page.locator('form#login-form input[name="login[username]"]').fill(auth['username'])
        page.locator('form#login-form input[name="login[password]"]').fill(auth['password'])
        page.get_by_role('button',name='Sign In',exact=True).first.click()
        page.wait_for_url(lambda u:'/customer/account/login' not in str(u),timeout=60000,wait_until='domcontentloaded')
    elif site.domain=='reddit':
        page.goto(site.url+'/login',wait_until='domcontentloaded',timeout=60000)
        page.get_by_label('Username',exact=True).fill(auth['username'])
        page.get_by_label('Password',exact=True).fill(auth['password'])
        page.get_by_role('button',name='Log in',exact=True).click()
        page.wait_for_url(lambda u:urlsplit(str(u)).path!='/login',timeout=60000,wait_until='domcontentloaded')
    else:raise ValueError('Site authentication not implemented')


SHOPPING_FORM_READY = """() => {
    const field=document.querySelector('form#login-form input[name="form_key"]');
    const entry=document.cookie.split(';').map(s=>s.trim()).find(s=>s.startsWith('form_key='));
    return !!(field && field.value && entry && decodeURIComponent(entry.slice(9))===field.value);
}"""


def wait_shopping_customer_data(page):
    """Opt-in login readiness experiment; no section invalidation or reload.

    Wait for Magento's native initialization promise so its form-submit listener
    can observe login. This does not modify customer data or fabricate cookies.
    """
    page.wait_for_function("() => typeof require === 'function'",timeout=15000)
    ready=page.evaluate("""() => new Promise(resolve => {
        let done=false;
        const finish=value=>{if(!done){done=true;clearTimeout(timer);resolve(value)}};
        const timer=setTimeout(()=>finish(false),15000);
        require(['Magento_Customer/js/customer-data'],data=>{
            if(typeof data.getInitCustomerData!=='function'){finish(false);return;}
            data.getInitCustomerData().done(()=>finish(true)).fail(()=>finish(false));
        },()=>finish(false));
    })""")
    if ready is not True:raise RuntimeError('Native customer-data initialization did not complete before login')


def login(page,site,auth,*,wait_for_customer_data=False):
    from .io_utils import atomic_write_json
    import time
    started=time.monotonic()
    try:
        _login(page,site,auth,wait_for_customer_data=wait_for_customer_data)
        if hasattr(site,'logs'):atomic_write_json(site.logs/'auth-result.json',{'status':'authenticated','domain':getattr(site,'domain','unknown'),'path':urlsplit(page.url).path,'seconds':time.monotonic()-started})
    except Exception as exc:
        if hasattr(site,'logs'):
            info={'status':'failed','domain':getattr(site,'domain','unknown'),'path':urlsplit(page.url).path,'error_type':type(exc).__name__,'seconds':time.monotonic()-started}
            try:
                info['errors']=page.locator('.message-error,.alert-danger,[role=alert]').all_text_contents()
                info['document_ready_state']=page.evaluate('document.readyState')
                if getattr(site,'domain',None)=='shopping':info['form_cookie_synchronized']=page.evaluate(SHOPPING_FORM_READY)
            except Exception as capture_error:info['capture_error_type']=type(capture_error).__name__
            # No passwords, form tokens, cookies or POST bodies are recorded.
            atomic_write_json(site.logs/'auth-result.json',info)
        raise

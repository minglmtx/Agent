"""Read native search/filter results; evaluator references never enter actor input."""
from urllib.parse import urlsplit, parse_qsl, urlencode
from .catalog_state import read_catalog_state, collection_scope


def search_scope(url):
    scope = collection_scope(url)
    # The native advanced form always supplies USD, also the website default.
    if scope['path'] == '/catalogsearch/advanced/result/':
        if scope['filters'].get('price[currency]') == ['USD']:
            del scope['filters']['price[currency]']
    return scope


def read_search_state(page):
    classes=(page.locator('body').get_attribute('class') or '').split()
    result_page=bool({'catalog-category-view','catalogsearch-result-index','catalogsearch-advanced-result'} & set(classes))
    catalog = read_catalog_state(page) if result_page else {'present':False}
    catalog.pop('scope', None)
    criteria = page.locator('.search.summary .item').evaluate_all("""es => es.map(e => ({
        label: e.querySelector('strong')?.innerText.trim().replace(/:$/, ''),
        value: Array.from(e.childNodes).filter(n => n.nodeType === Node.TEXT_NODE).map(n => n.textContent).join('').trim()
    }))""")
    filters = page.locator('.filter-current .item').evaluate_all("""es => es.map(e => ({
        label:e.querySelector('.filter-label')?.innerText.trim(),
        value:e.querySelector('.filter-value')?.innerText.trim()
    }))""")
    if any(not r.get('label') or not r.get('value') for r in criteria + filters):
        raise ValueError('Incomplete native applied search/filter criterion')
    headings = page.locator('h1').all_inner_texts()
    messages = page.locator('main .message').all_inner_texts()
    empty = any("We can't find any items matching these search criteria." in m or
                "Your search returned no results." in m for m in messages)
    return {'scope':search_scope(page.url), 'heading':' '.join(headings).strip(),
            'criteria':sorted(criteria, key=lambda r:(r['label'],r['value'])),
            'filters':sorted(filters, key=lambda r:(r['label'],r['value'])),
            'empty_result':empty, 'catalog':catalog}


def reference_path(contract, state=None):
    """Same requested result set, with any valid terminal pagination/layout/sort."""
    parts = urlsplit(contract['search']['target_path'])
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if contract['search']['kind']=='advanced':
        # Reproduce native form serialization: Magento requires both range ends
        # (an empty string for an open end), and currency controls presentation.
        native={k:'' for k in ('name','sku','description','short_description','price[from]','price[to]')}
        native['price[currency]']='USD'
        query=native | query
    cat = (state or {}).get('catalog', {})
    if cat.get('present'):
        if cat.get('order') not in ('position','name','price','relevance') or cat.get('direction') not in ('asc','desc'):
            raise ValueError('Unknown native catalog ordering')
        # List and grid have different native page-size options (default list=10).
        # This is a captured positive integer, not an arbitrary supplied query.
        if cat.get('mode') not in ('grid','list') or type(cat.get('limit')) is not int or cat['limit']<=0:
            raise ValueError('Unknown native catalog layout')
        if type(cat.get('page')) is not int or not 1 <= cat['page'] <= 100000:
            raise ValueError('Invalid terminal page number')
        query.update({'product_list_order':cat['order'], 'product_list_dir':cat['direction'],
                      'product_list_mode':cat['mode'], 'product_list_limit':str(cat['limit']), 'p':str(cat['page'])})
    return parts.path + ('?' + urlencode(query) if query else '')


def private_reference(site, contract, auth, state=None, *, browser=None):
    """Read the native requested page in a separate context after actor termination."""
    from .site_auth import login
    from .browser_request_policy import install_local_network_policy
    def read(browser):
        ctx = browser.new_context(viewport={'width':1280,'height':720})
        try:
            install_local_network_policy(ctx, urlsplit(site.url).netloc)
            page = ctx.new_page(); page.set_default_timeout(10000)
            login(page, site, auth)
            response = page.goto(site.url + reference_path(contract, state), wait_until='load', timeout=30000)
            if response is None or response.status != 200:
                raise ValueError('Independent search reference page unavailable')
            return read_search_state(page)
        finally:
            ctx.close()
    if browser is not None:return read(browser)
    # In online evaluation BrowserGym's global manager is still alive after
    # closing the actor browser. Own a separate browser, not a second manager.
    from browsergym.core import _get_global_playwright
    browser = _get_global_playwright().chromium.launch(headless=True)
    try:return read(browser)
    finally:browser.close()

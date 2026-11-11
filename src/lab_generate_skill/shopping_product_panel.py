"""Product panel state and approved reviews; no automatic actor navigation."""
from .site_database import select_rows
from collections import Counter
from urllib.parse import urlsplit,parse_qs

def description_reference(site,product_id):
    rows=select_rows(site,f"SELECT v.store_id,v.value FROM catalog_product_entity_text v JOIN eav_attribute a ON a.attribute_id=v.attribute_id WHERE v.entity_id={int(product_id)} AND a.entity_type_id=4 AND a.attribute_code='description' AND v.store_id IN (0,1) ORDER BY v.store_id")
    effective=[r for r in rows if r['store_id']==1]or[r for r in rows if r['store_id']==0]
    if len(effective)!=1 or not effective[0]['value'].strip():raise ValueError('Native description missing or ambiguous')
    return effective[0]['value']

def description_text(html):
    from bs4 import BeautifulSoup
    from .product_description_fields import clean_table_text
    return clean_table_text(BeautifulSoup(html,'html.parser').get_text(' ',strip=True))

def review_reference(site,product_id):
    return select_rows(site,'SELECT r.review_id,r.entity_pk_value,r.status_id,r.created_at,d.title,d.detail,d.nickname FROM review r JOIN review_detail d ON d.review_id=r.review_id WHERE r.entity_pk_value='+str(int(product_id))+' ORDER BY r.review_id')

def verify_panel_reference(site,spec):
    if spec['mode']=='description':
        if description_reference(site,spec['product_id'])!=spec['description_html']:raise ValueError('Product description reference changed')
        return
    if review_reference(site,spec['product_id'])!=spec['reviews']:raise ValueError('Product review reference changed')

def read_product_panel(page):
    return page.evaluate(r'''() => {
      const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      const reviews=document.querySelector('#reviews'),form=document.querySelector('#review-form');
      const description=document.querySelector('#description .product.attribute.description .value');
      const current=[...new Set([...document.querySelectorAll('#reviews .pages .item.current')].filter(visible)
        .map(e=>(e.innerText.match(/\d+/g)||[])).filter(a=>a.length===1).map(a=>Number(a[0])))];
      const pages=[...new Set([...document.querySelectorAll('#reviews .pages a[href]')].filter(visible)
        .map(e=>Number(new URL(e.href,location.href).searchParams.get('p') || '1')).filter(n=>Number.isInteger(n)&&n>0))];
      return {product_id:document.querySelector('#product_addtocart_form input[name="product"]')?.value || null,
        product_name:document.querySelector('h1.page-title')?.innerText.trim() || '',
        reviews_visible:visible(reviews),form_visible:visible(form),
        description_visible:visible(description),description_text:description?.innerText||'',
        form_fields:form?[...form.querySelectorAll('input:not([type=hidden]),textarea')].filter(visible).map(e=>e.name).sort():[],
        review_page:current.length===1?current[0]:null,review_other_pages:pages,
        rows:reviews?[...reviews.querySelectorAll('.review-item')].filter(visible).map(e=>({
          title:e.querySelector('.review-title')?.innerText.trim(),detail:e.querySelector('.review-content')?.innerText.trim()})):[]};
    }''')

def panel_checks(spec,state):
    if not isinstance(state,dict) or not isinstance(state.get('rows'),list):raise ValueError('Missing product panel capture')
    mode=spec['mode']
    if mode not in ('reviews','review_form','description'):raise ValueError('Unsupported product panel')
    checks={'panel_product_identity':state.get('product_id')==str(spec['product_id']) and state.get('product_name')==spec['product_name']}
    if mode=='description':
        from .product_description_fields import clean_table_text
        expected=description_text(spec['description_html'])
        if not expected:raise ValueError('Empty native product description reference')
        checks.update(product_description_displayed=state.get('description_visible')is True,
                      complete_product_description=clean_table_text(state.get('description_text',''))==expected)
    elif mode=='reviews':
        approved=[r for r in spec['reviews'] if int(r['status_id'])==1]
        normalize=lambda s:' '.join(s.split())
        expected=sorted((normalize(r['title']),normalize(r['detail'])) for r in approved)
        actual=sorted((normalize(r['title']),normalize(r['detail'])) for r in state['rows'])
        if spec.get('review_pages'):
            pages=spec['review_pages'];keys=sorted(int(k) for k in pages)
            if keys!=list(range(1,len(keys)+1)) or not all(pages[str(k)] for k in keys):raise ValueError('Incomplete native review-page references')
            full=[(normalize(r['title']),normalize(r['detail'])) for rs in pages.values() for r in rs]
            if Counter(full)!=Counter(expected):raise ValueError('Native pages do not cover the approved review records exactly')
            current=state.get('review_page')
            # This family means opening a real review page, not reading all
            # pages. Never infer that the actor visited pages absent in history.
            checks['review_page_identity']=type(current) is int and current in keys
            expected=sorted((normalize(r['title']),normalize(r['detail'])) for r in pages.get(str(current),[]))
            checks['review_pagination_available']=set(state.get('review_other_pages',[]))==set(keys)-{current}
        elif not 0<len(approved)<=10:raise ValueError('Requires separate empty or paginated review adapter')
        checks.update(product_reviews_displayed=state.get('reviews_visible') is True,
                      approved_review_content=bool(expected) and expected==actual)
    else:
        checks.update(review_form_displayed=state.get('form_visible') is True,
                      review_form_fields={'nickname','title','detail'}<=set(state.get('form_fields',[])))
    return checks

def open_panel_control(page,mode):
    """Native scripted positive control only; never called by the actor runtime."""
    page.wait_for_function("() => !!(window.jQuery && jQuery('.product.data.items').data('mageTabs'))",timeout=15000)
    if mode=='description':
        if not page.locator('#description').is_visible():page.locator('a[href="#description"]').first.click()
        page.locator('#description .product.attribute.description .value').wait_for(state='visible',timeout=15000)
        return
    if not page.locator('#reviews').is_visible():page.locator('a[href="#reviews"]').first.click()
    page.locator('#reviews').wait_for(state='visible',timeout=15000)
    if mode=='reviews':page.locator('#reviews .review-item').first.wait_for(state='visible',timeout=15000)
    else:page.locator('#review-form').wait_for(state='visible',timeout=15000)


def set_review_page_control(page,number):
    """Follow a native pager link during controls only; never an actor tool."""
    if read_product_panel(page).get('review_page')==number:return
    links=page.locator('#reviews .pages a[href]')
    candidates=[link for link in links.all() if link.is_visible() and
                parse_qs(urlsplit(link.get_attribute('href')).query).get('p',['1'])==[str(number)]]
    if not candidates:raise ValueError('Native review page link missing')
    candidates[0].click(timeout=10000)
    page.wait_for_function('''number=>{
      const es=[...document.querySelectorAll('#reviews .pages .item.current')].filter(e=>e.getClientRects().length);
      return es.length>0 && es.every(e=>{const a=e.innerText.match(/\\d+/g)||[];return a.length===1&&Number(a[0])===number;});
    }''',arg=number,timeout=15000)

FEEDBACK={'panel_product_identity':'The displayed panel belongs to the requested product.',
          'product_description_displayed':'The product Details tab is expanded and its description is displayed.',
          'complete_product_description':'The displayed description matches the complete native content of the requested product.',
          'product_reviews_displayed':'The product review section is displayed.',
          'approved_review_content':'The visible review page contains the expected approved review content for the requested product.',
          'review_page_identity':'The displayed review page is a valid page for the requested product.',
          'review_pagination_available':'The native controls provide access to the other review pages.',
          'review_form_displayed':'The product review form is displayed.',
          'review_form_fields':'The native review fields are available.'}

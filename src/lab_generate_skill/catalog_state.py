"""Public native Magento toolbar and rendered list state, without hidden answers."""
import re
from urllib.parse import urlsplit,parse_qs
from decimal import Decimal

TOOLBAR_KEYS={'product_list_order','product_list_dir','product_list_mode','product_list_limit','p'}


def collection_scope(url):
    parts=urlsplit(url);query=parse_qs(parts.query,keep_blank_values=True)
    # Magento's native toolbar adds the default controller action to search URLs.
    path=parts.path
    if path in ('/catalogsearch/result/index/','/catalogsearch/result/index'):
        path='/catalogsearch/result/'
    return {'path':path,'filters':{k:v for k,v in query.items() if k not in TOOLBAR_KEYS and v!=['']}}


def unique(values,label):
    values=list(dict.fromkeys(values))
    if len(values)!=1:raise ValueError('Missing or conflicting catalog '+label)
    return values[0]


def read_catalog_state(page):
    wrappers=page.locator('.products.wrapper:visible')
    if wrappers.count()==0:return {'present':False,'scope':collection_scope(page.url)}
    if wrappers.count()!=1:raise ValueError('Ambiguous product list')
    # Both toolbars can expose the same value; they must agree.
    order=unique(page.locator('[data-role="sorter"]').evaluate_all('es=>es.map(e=>e.value)'),'sort field')
    limit=int(unique(page.locator('[data-role="limiter"]').evaluate_all('es=>es.map(e=>e.value)'),'page size'))
    next_direction=unique(page.locator('[data-role="direction-switcher"]').evaluate_all('es=>es.map(e=>e.dataset.value)'),'sort direction')
    if next_direction not in ('asc','desc'):raise ValueError('Unknown native sort direction')
    direction='asc' if next_direction=='desc' else 'desc'
    mode=unique(page.locator('.modes-mode.active').evaluate_all('es=>es.map(e=>e.dataset.value)'),'view mode')
    classes=wrappers.get_attribute('class').split()
    if mode not in ('grid','list') or 'products-'+mode not in classes:raise ValueError('Active mode disagrees with rendered layout')
    amounts=page.locator('.toolbar-amount').evaluate_all('es=>es.map(e=>Array.from(e.querySelectorAll(".toolbar-number")).map(n=>n.innerText.trim()))')
    totals=[]
    for values in amounts:
        if not values or not re.fullmatch(r'[\d,]+',values[-1]):raise ValueError('Missing native total item count')
        totals.append(int(values[-1].replace(',','')))
    total=unique(totals,'total count')
    items=wrappers.locator('li.product-item').evaluate_all("es=>es.map(e=>({name:e.querySelector('.product-item-link')?.innerText.trim(),url:e.querySelector('.product-item-link')?.href,price:e.querySelector('[data-price-type=finalPrice]')?.getAttribute('data-price-amount')}))")
    if not items:raise ValueError('Catalog present with no rendered products')
    for row in items:
        if not row['name'] or not row['url'] or row['price'] is None:raise ValueError('Incomplete rendered product')
        if not Decimal(row['price']).is_finite():raise ValueError('Invalid product price')
        row['path']=urlsplit(row.pop('url')).path
    if len({r['path'] for r in items})!=len(items):raise ValueError('Duplicate catalog products')
    current=page.locator('.pages .item.current .page').all_inner_texts()
    if current:
        pages=[]
        for value in current:
            numbers=re.findall(r'\d+',value)
            if len(numbers)!=1:raise ValueError('Ambiguous current page number')
            pages.append(int(numbers[0]))
        number=unique(pages,'page number')
    elif total<=limit:number=1
    else:raise ValueError('Missing page indicator for multipage catalog')
    return {'present':True,'scope':collection_scope(page.url),'heading':page.locator('h1').inner_text().strip(),'order':order,'direction':direction,'limit':limit,'mode':mode,'page':number,'total':total,'items':items}

"""Explicit catalog facts and native review dates, independently read from UI/DB.

These readers never infer an absent accessory from silence and never classify
free review prose. A negative-review date is supported only for a sole approved
review with explicit low ratings. Unsupported/ambiguous sources fail admission.
"""
import re
from datetime import datetime
from .site_database import select_rows
from .product_description_fields import description_fact, clean_table_text


def only(rows):
    if len(rows) != 1:
        raise ValueError('Missing or ambiguous catalog fact')
    return rows[0]


def name_fact(name, field):
    if field == 'magnification':
        hits = re.findall(r'(?<![\w.])(\d+(?:\.\d+)?)\s*[x×]\s+magnification\b', name, re.I)
        return only(hits)
    if field == 'power_cord_included':
        negative = re.findall(r'\b(?:no|without)\s+(?:a\s+)?power cord\b', name, re.I)
        positive = re.findall(r'\bwith\s+(?:a\s+)?power cord\b|\bpower cord\s+included\b', name, re.I)
        if bool(negative) == bool(positive):
            raise ValueError('Accessory inclusion absent or contradictory')
        return 'no' if negative else 'yes'
    raise ValueError('Unsupported title fact')


def reference(site, q):
    ident = q['object_id']
    if type(ident) is not int or ident <= 0:
        raise ValueError('Invalid product identity')
    from .shopping_product_details import product_reference
    product = only(product_reference(site, [ident]))
    if product['name'] != q['object_name']:
        raise ValueError('Catalog product identity changed')
    state = {'product': product}
    values = {}
    for field in q['fields']:
        if field == 'material':
            values[field] = description_fact(site, ident, 'Material')
        elif field in ('magnification', 'power_cord_included'):
            values[field] = name_fact(product['name'], field)
        elif field in ('material_types','colors'):
            group_label='Material Type' if field=='material_types' else 'Color'
            options = select_rows(site, f"SELECT o.option_id,o.type,t.store_id,t.title FROM catalog_product_option o JOIN catalog_product_option_title t ON t.option_id=o.option_id WHERE o.product_id={ident} AND t.store_id IN (0,1) ORDER BY o.option_id,t.store_id")
            grouped = {}
            for row in options:
                grouped.setdefault(row['option_id'], []).append(row)
            effective = [only([r for r in rs if r['store_id']==1] or [r for r in rs if r['store_id']==0]) for rs in grouped.values()]
            option = only([r for r in effective if r['title']==group_label])
            if option['type'] != 'radio':
                raise ValueError('Unvalidated option widget')
            rows = select_rows(site, f"SELECT v.option_type_id,t.store_id,t.title FROM catalog_product_option_type_value v JOIN catalog_product_option_type_title t ON t.option_type_id=v.option_type_id WHERE v.option_id={int(option['option_id'])} AND t.store_id IN (0,1) ORDER BY v.option_type_id,t.store_id")
            groups = {}
            for row in rows:
                groups.setdefault(row['option_type_id'], []).append(row)
            titles = [only([r for r in rs if r['store_id']==1] or [r for r in rs if r['store_id']==0])['title'] for rs in groups.values()]
            if not titles or any(not t.strip() for t in titles) or len(set(titles)) != len(titles):
                raise ValueError('Missing or duplicate option labels')
            values[field] = [{'name': t} for t in titles]
            state['options'] = options; state['option_values'] = rows
        elif field == 'negative_review_date':
            rows = select_rows(site, f"SELECT r.review_id,r.created_at,d.title,d.detail,d.nickname FROM review r JOIN review_detail d ON d.review_id=r.review_id JOIN review_store s ON s.review_id=r.review_id AND s.store_id=1 WHERE r.entity_pk_value={ident} AND r.status_id=1 AND r.entity_id=(SELECT entity_id FROM review_entity WHERE entity_code='product') ORDER BY r.review_id")
            review = only(rows)
            votes = select_rows(site, f"SELECT rating_id,value,percent FROM rating_option_vote WHERE review_id={int(review['review_id'])} ORDER BY rating_id")
            if not votes or any(int(v['value']) not in (1,2) or int(v['percent']) != 20*int(v['value']) for v in votes):
                raise ValueError('Sole approved review has no unambiguous low rating')
            values[field] = datetime.strptime(str(review['created_at']), '%Y-%m-%d %H:%M:%S').date().isoformat()
            state['review'] = review; state['votes'] = votes
        else:
            raise ValueError('Unsupported catalog fact')
    return {'object_id': 'shopping_catalog_facts:'+str(ident), 'values': values, 'source_state': state}


def ui_values(page, q):
    from .shopping_product_details import read_product_details
    identity = read_product_details(page)
    if identity['product_id'] != str(q['object_id']) or identity['name'] != q['object_name']:
        raise ValueError('Wrong visible catalog product')
    values = {}
    for field in q['fields']:
        if field == 'material':
            rows = page.locator('.product.attribute.description tr').evaluate_all("rs=>rs.map(r=>[...r.children].filter(e=>['TH','TD'].includes(e.tagName)).map(e=>e.innerText))")
            values[field] = only([clean_table_text(r[1]) for r in rows if len(r)==2 and clean_table_text(r[0]).rstrip(':').casefold()=='material' and clean_table_text(r[1])])
        elif field in ('magnification', 'power_cord_included'):
            values[field] = name_fact(page.locator('h1 .base').inner_text().strip(), field)
        elif field in ('material_types','colors'):
            group_label='Material Type' if field=='material_types' else 'Color'
            # Native custom-option labels, not a substring search over the page.
            fields = page.locator('.product-options-wrapper .field').all()
            groups = [f for f in fields if f.locator(':scope > label.label').count()==1 and f.locator(':scope > label.label').inner_text().strip()==group_label]
            group = only(groups)
            group.wait_for(state='visible', timeout=10000)
            radios = group.locator('input[type=radio]').all()
            titles = []
            for radio in radios:
                # Magento normally uses an explicit for attribute.
                ident = radio.get_attribute('id')
                labels = page.locator('label').evaluate_all('(es,id)=>es.filter(e=>e.htmlFor===id && e.getClientRects().length).map(e=>e.innerText.trim())', ident)
                titles.append(only(labels))
            if not titles or len(set(titles))!=len(titles):
                raise ValueError('Public option labels missing or duplicated')
            values[field] = [{'name': t} for t in titles]
        elif field == 'negative_review_date':
            from .shopping_product_panel import open_panel_control
            open_panel_control(page, 'reviews')  # Admission reader only, never actor.
            items = page.locator('#reviews .review-item').all()
            review = only(items)
            percentages = review.locator('.rating-result').evaluate_all('es=>es.map(e=>e.getAttribute("title") || e.innerText)')
            if not percentages or any(not re.fullmatch(r'\s*(?:20|40)\s*%\s*', x) for x in percentages):
                raise ValueError('Public review has no explicit low rating')
            date = review.locator('.review-date time').inner_text().strip()
            values[field] = datetime.strptime(date, '%m/%d/%y').date().isoformat()
        else:
            raise ValueError('Unsupported public catalog fact')
    return values

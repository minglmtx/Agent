"""Typed account/cart references from the pinned Magento snapshot and public UI."""
from decimal import Decimal
import re
from .site_database import select_rows

CART_RECORD_SHAPES=({'name':'string'}, {'name':'string','quantity':'integer'},
                    {'name':'string','quantity':'integer','unit_price':'decimal'})


def one(rows):
    if len(rows)!=1:raise ValueError('Missing or ambiguous shopping reference')
    return rows[0]


def reference(site,q):
    ident=q['object_id'];customer=q['customer_id'];family=q['family'];fields=q['fields']
    if type(customer) is not int or customer<=0:raise ValueError('Invalid customer binding')
    account=one(select_rows(site,f'SELECT entity_id,firstname,lastname FROM customer_entity WHERE entity_id={customer}'))
    if account['firstname']+' '+account['lastname']!=q['customer_name']:raise ValueError('Account identity changed')
    values={}
    if family=='shopping_cart':
        cart=one(select_rows(site,f'SELECT entity_id,customer_id,items_qty,subtotal FROM quote WHERE entity_id={ident} AND customer_id={customer} AND is_active=1'))
        item_columns='item_id,product_id,parent_item_id,qty,price,row_total'+(',name' if 'items' in fields else '')
        items=select_rows(site,f'SELECT {item_columns} FROM quote_item WHERE quote_id={ident} ORDER BY item_id')
        if any(x['parent_item_id'] is not None for x in items):raise ValueError('Nested/configurable cart rows require separate validated accounting')
        if Decimal(str(cart['items_qty']))!=sum(Decimal(str(x['qty'])) for x in items):raise ValueError('Stored cart quantity disagrees with items')
        for key in fields:
            if key=='item_count':values[key]=str(cart['items_qty'])
            elif key=='items_subtotal':values[key]=str(cart['subtotal'])
            elif key=='quantity':
                product=q['product_id']
                if type(product) is not int or product<=0:raise ValueError('Invalid product binding')
                values[key]=str(one([x for x in items if x['product_id']==product])['qty'])
            elif key=='items':
                shape=q.get('record_fields',{}).get(key)
                if fields[key]!='record_set' or shape not in CART_RECORD_SHAPES:
                    raise ValueError('Unsupported cart record fields')
                values[key]=[{k:{'name':x['name'],'quantity':str(x['qty']),'unit_price':str(x['price'])}[k] for k in shape} for x in items]
            else:raise ValueError('Unsupported cart field')
        state={'cart':cart,'items':items}
    elif family=='shopping_newsletter':
        if ident!=customer or set(fields)!={'subscription_status'}:raise ValueError('Invalid newsletter binding')
        rows=select_rows(site,f'SELECT customer_id,subscriber_status FROM newsletter_subscriber WHERE customer_id={customer}')
        if len(rows)>1:raise ValueError('Ambiguous newsletter state')
        flag=int(rows[0]['subscriber_status']) if rows else 3
        if flag not in (1,2,3,4):raise ValueError('Unknown native newsletter status')
        values['subscription_status']='Subscribed' if flag==1 else 'Not subscribed'
        state={'customer_id':customer,'subscription_rows':rows}
    elif family=='shopping_order':
        order=one(select_rows(site,f'SELECT entity_id,customer_id,increment_id,status,grand_total FROM sales_order WHERE entity_id={ident} AND customer_id={customer}'))
        if order['increment_id']!=q['order_number']:raise ValueError('Wrong order number')
        if set(fields)!={'order_status'}:raise ValueError('Unsupported order field')
        label=one(select_rows(site,"SELECT label FROM sales_order_status WHERE status='"+str(order['status']).replace("'","''")+"'"))['label']
        values['order_status']=label;state=order
    elif family=='shopping_address':
        slot=q.get('address_slot')
        if slot not in ('default_billing','default_shipping'):raise ValueError('Unsupported address scope')
        binding=one(select_rows(site,f'SELECT {slot} AS address_id FROM customer_entity WHERE entity_id={customer}'))
        if binding['address_id']!=ident:raise ValueError('Requested default address identity changed')
        address=one(select_rows(site,f'SELECT entity_id,parent_id,firstname,lastname,street,city,region,postcode,country_id,telephone FROM customer_address_entity WHERE entity_id={ident} AND parent_id={customer}'))
        all_values={'name':address['firstname']+' '+address['lastname'],'street':address['street'],'city':address['city'],'region':address['region'],'postal_code':address['postcode'],'country_code':address['country_id'],'telephone':address['telephone']}
        if not set(fields)<=set(all_values):raise ValueError('Unsupported address field')
        values={k:all_values[k] for k in fields};state={'default_address':binding,'address':address}
    else:raise ValueError('Unsupported shopping query family')
    # Never silently truncate fractional quantities to integer.
    for key,kind in fields.items():
        if kind=='integer':
            value=Decimal(values[key])
            if value!=value.to_integral_value():raise ValueError('Requested integer field is fractional')
            values[key]=int(value)
    return {'object_id':family+':'+str(ident),'values':values,'source_state':state}


def price_value(text):
    text=text.strip()
    if not re.fullmatch(r'\$\d[\d,]*\.\d{2}',text):raise ValueError('Unexpected rendered USD price')
    return Decimal(text[1:].replace(',',''))


def street_input_value(rows):
    indexed=[]
    for row in rows:
        m=re.fullmatch(r'street\[(\d+)\]',row['name'])
        if not m:raise ValueError('Unexpected native street field name')
        indexed.append((int(m[1]),row['value']))
    indexed.sort()
    if not indexed or [i for i,v in indexed]!=list(range(len(indexed))) or not indexed[0][1]:
        raise ValueError('Missing or ambiguous native street fields')
    values=[v for i,v in indexed]
    while values and not values[-1]:values.pop()
    return '\n'.join(values)


def ui_values(page,q):
    family=q['family'];fields=q['fields'];values={}
    if family=='shopping_cart':
        table=page.locator('#shopping-cart-table');table.wait_for(state='visible',timeout=15000)
        items=table.locator('tbody.cart.item')
        if not items.count():raise ValueError('No visible cart records')
        for key in fields:
            if key=='item_count':
                quantities=items.locator('input.qty').evaluate_all('es=>es.map(e=>e.value)')
                if len(quantities)!=items.count():raise ValueError('Cart row quantity missing')
                values[key]=str(sum(Decimal(x) for x in quantities))
            elif key=='items_subtotal':
                totals=items.locator('.col.subtotal .price').all_text_contents()
                if len(totals)!=items.count():raise ValueError('Cart row subtotal missing')
                values[key]=str(sum(price_value(x) for x in totals))
            elif key=='quantity':
                item=items.filter(has=page.get_by_role('link',name=q['product_name'],exact=True))
                if item.count()!=1:raise ValueError('Requested public cart product missing or ambiguous')
                values[key]=item.locator('input.qty').input_value()
            elif key=='items':
                shape=q.get('record_fields',{}).get(key)
                if fields[key]!='record_set' or shape not in CART_RECORD_SHAPES:
                    raise ValueError('Unsupported cart UI record fields')
                rows=[]
                for item in items.all():
                    name=item.locator('.product-item-name a').inner_text().strip()
                    observed={'name':name}
                    if 'quantity' in shape:observed['quantity']=item.locator('input.qty').input_value()
                    if 'unit_price' in shape:observed['unit_price']=str(price_value(item.locator('.col.price .price').inner_text()))
                    rows.append(observed)
                values[key]=rows
            else:raise ValueError('Unsupported cart UI field')
    elif family=='shopping_newsletter':
        contact=page.locator('.box-information .box-content').inner_text()
        if q['customer_name'] not in contact:raise ValueError('Wrong visible account')
        text=page.locator('.box-newsletter .box-content').inner_text().strip()
        if text=="You aren't subscribed to our newsletter.":value='Not subscribed'
        elif text=='You are subscribed to "General Subscription".':value='Subscribed'
        else:raise ValueError('Unrecognized public newsletter status')
        values['subscription_status']=value
    elif family=='shopping_order':
        heading=page.locator('h1').inner_text()
        if not re.search(r'\b'+re.escape(q['order_number'])+r'\b',heading):raise ValueError('Wrong visible order')
        values['order_status']=page.locator('.order-status').inner_text().strip()
    elif family=='shopping_address':
        from urllib.parse import urlsplit
        if urlsplit(page.url).path!='/customer/address/edit/id/'+str(q['object_id'])+'/':raise ValueError('Wrong visible address identity')
        form=page.locator('#form-validate');form.wait_for(state='visible',timeout=15000)
        country=form.locator('[name="country_id"]').input_value()
        region_select=form.locator('select[name="region_id"]')
        if region_select.is_visible():region=region_select.locator('option:checked').inner_text().strip()
        else:region=form.locator('input[name="region"]').input_value()
        all_values={'name':form.locator('[name="firstname"]').input_value()+' '+form.locator('[name="lastname"]').input_value(),
                    'street':street_input_value(form.locator('input[name^="street["]').evaluate_all('es=>es.map(e=>({name:e.name,value:e.value}))')),
                    'city':form.locator('[name="city"]').input_value(),'region':region,'postal_code':form.locator('[name="postcode"]').input_value(),
                    'country_code':country,'telephone':form.locator('[name="telephone"]').input_value()}
        values={k:all_values[k] for k in fields}
    else:raise ValueError('Unsupported shopping UI family')
    return values

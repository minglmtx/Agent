"""Native checkout answers with protected cart/account/order invariants.

Private reference values come from two independent native capability runs and
are checked against live UI again during task admission. Quote totals/addresses
are native caches populated by visiting Review & Payments; they are not the
protected cart contents or saved address book. No order may be placed.
"""
import re
from decimal import Decimal
from .site_database import select_rows
from .shopping_checkout import checkout_state, read_checkout_page

FIELD_TYPES = {'shipping_method': 'string', 'shipping_cost': 'decimal',
               'order_total': 'decimal', 'subtotal': 'decimal', 'total_correct': 'string',
               'shipping_methods': 'record_set', 'payment_methods': 'record_set',
               'alternative_shipping_available': 'string', 'free_shipping_available':'string',
               'shipping_address_lines':'record_set'}
RECORD_FIELDS = {'shipping_methods': {'carrier': 'string', 'method': 'string', 'cost': 'decimal'},
                 'payment_methods': {'method': 'string'},
                 'shipping_address_lines': {'line':'integer','text':'string'}}


def validate(q):
    if q.get('family') != 'shopping_checkout_values': raise ValueError('Unsupported query family')
    if any(type(q.get(k)) is not int or q[k] <= 0 for k in ('object_id', 'customer_id')):
        raise ValueError('Explicit customer and active cart required')
    if not q.get('fields') or any(FIELD_TYPES.get(k) != v for k,v in q['fields'].items()):
        raise ValueError('Unsupported checkout output fields')
    if set(q.get('reference_values', {})) != set(q['fields']): raise ValueError('Missing private native reference')
    for field in set(q['fields']) & RECORD_FIELDS.keys():
        if q.get('record_fields', {}).get(field) != RECORD_FIELDS[field]: raise ValueError('Invalid record schema')
    if 'alternative_shipping_available' in q['fields']:
        if not isinstance(q.get('from_shipping_method'),str) or not q['from_shipping_method'].strip():
            raise ValueError('Original shipping method must be explicit')
        if q.get('answer_labels',{}).get('alternative_shipping_available')!=['yes','no']:
            raise ValueError('Availability answers require explicit yes/no labels')
    if 'free_shipping_available'in q['fields']and q.get('answer_labels',{}).get('free_shipping_available')!=['yes','no']:
        raise ValueError('Free shipping availability requires explicit yes/no labels')


def protected_state(state):
    return {k:state[k] for k in ('cart','account','saved_addresses','orders')}


def cache_matches_defaults(state, q):
    """Allow native cache population, not changing the intended delivery address."""
    if len(state['account']) != 1: return False
    account = state['account'][0]
    addresses = {r['entity_id']:r for r in state['saved_addresses']}
    fields = ('firstname','lastname','street','city','country_id','region_id','region','postcode','telephone')
    for row in state['quote_addresses']:
        kind = row['address_type']
        if kind not in ('billing','shipping'): return False
        target = addresses.get(account.get('default_'+kind))
        if not target: return False
        populated = row.get('customer_address_id') is not None or any(row.get(k) is not None for k in fields)
        if populated and (row.get('customer_address_id') != target['entity_id'] or any(row.get(k)!=target.get(k) for k in fields)):
            return False
        if kind == 'shipping' and row.get('shipping_method') is not None:
            if row['shipping_method'] not in q.get('native_shipping_rates', {}): return False
            if Decimal(row['shipping_amount']) != Decimal(q['native_shipping_rates'][row['shipping_method']]): return False
    return True


def reference(site, q):
    validate(q)
    rows = select_rows(site, f"SELECT entity_id,firstname,lastname,email FROM customer_entity WHERE entity_id={q['customer_id']}")
    if len(rows) != 1 or rows[0]['firstname']+' '+rows[0]['lastname'] != q['customer_name']:
        raise ValueError('Wrong checkout customer')
    state = checkout_state(site, rows[0]['email'])
    if state['cart']['cart_id'] != q['object_id'] or state['cart']['user_id'] != q['customer_id']:
        raise ValueError('Active checkout cart differs from reference')
    config = select_rows(site, "SELECT scope,scope_id,path,value FROM core_config_data WHERE path LIKE 'carriers/flatrate/%' OR path LIKE 'carriers/freeshipping/%' OR path IN ('payment/checkmo/active','payment/checkmo/title') ORDER BY path,scope,scope_id")
    return {'object_id':'shopping_checkout_values:'+str(q['object_id']),
            'values':q['reference_values'], 'source_state':protected_state(state), 'source_config':config,
            'quote_cache_matches_default_address_and_native_rates':cache_matches_defaults(state,q)}


def money(text):
    matches = re.findall(r'\$([\d,]+\.\d{2})', text)
    if len(matches) != 1: raise ValueError('Missing or ambiguous native USD amount')
    return str(Decimal(matches[0].replace(',', '')))


def values_from_capture(shipping, payment, fields, *, claimed_total=None, from_shipping_method=None):
    """Read independently captured native controls, never the private answers."""
    values = {}; methods = []
    for row in shipping['shipping_rows']:
        if not row['inputs']: continue
        cells = row['cells']
        if len(cells) != 4 or len(row['inputs']) != 1: raise ValueError('Unexpected native shipping row')
        methods.append({'carrier':cells[3].strip(), 'method':cells[2].strip(), 'cost':money(cells[1])})
    if not methods: raise ValueError('No available shipping methods')
    selected = [row for row in shipping['shipping_rows'] if any(i['checked'] for i in row['inputs'])]
    for field in fields:
        if field == 'shipping_methods': values[field] = methods
        elif field == 'shipping_address_lines':
            addresses=shipping.get('addresses',shipping.get('checkout',{}).get('addresses'))
            if not isinstance(addresses,list)or any(not isinstance(r,dict)or type(r.get('selected'))is not bool or not isinstance(r.get('text'),str)for r in addresses):
                raise ValueError('Native address selection state missing')
            chosen=[r for r in addresses if r['selected']]
            if len(chosen)!=1:raise ValueError('Unique selected shipping address required')
            lines=[s.strip()for s in chosen[0]['text'].splitlines()if s.strip()]
            if not lines:raise ValueError('Selected address text missing')
            values[field]=[{'line':i,'text':s}for i,s in enumerate(lines,1)]
        elif field == 'free_shipping_available':
            free=[]
            for row in shipping['shipping_rows']:
                if not row['inputs']or Decimal(money(row['cells'][1]))!=0:continue
                disabled=row['inputs'][0].get('disabled')
                if type(disabled)is not bool:raise ValueError('Free option enabled state missing')
                free.append(not disabled)
            values[field]='yes'if any(free)else 'no'
        elif field == 'alternative_shipping_available':
            if not isinstance(from_shipping_method,str) or not from_shipping_method.strip():
                raise ValueError('Original shipping method missing')
            labels=[r['carrier']+' - '+r['method']for r in methods]
            if labels.count(from_shipping_method)!=1:
                raise ValueError('Original shipping option missing or ambiguous')
            enabled=[]
            for row in shipping['shipping_rows']:
                if not row['inputs']:continue
                label=row['cells'][3].strip()+' - '+row['cells'][2].strip()
                if label==from_shipping_method:continue
                disabled=row['inputs'][0].get('disabled')
                if type(disabled)is not bool:raise ValueError('Alternative option enabled state missing')
                enabled.append(not disabled)
            values[field]='yes' if any(enabled)else 'no'
        elif field == 'payment_methods':
            labels = [x.strip() for x in payment['payment_labels'] if x.strip()]
            if not labels or len(set(labels)) != len(labels): raise ValueError('Missing or ambiguous payment methods')
            values[field] = [{'method':x} for x in labels]
        elif field == 'shipping_method':
            if len(selected) != 1: raise ValueError('A uniquely selected native shipping method is required')
            cells = selected[0]['cells']; values[field] = cells[3].strip()+' - '+cells[2].strip()
        elif field in ('subtotal','shipping_cost','order_total','total_correct'):
            def amount(token):
                matches = [r['value'] for r in payment['summary_rows'] if token in r['class_name'].split()]
                if len(matches) != 1: raise ValueError('Native total row missing: '+token)
                return money(matches[0])
            if field == 'total_correct':
                if claimed_total is None: raise ValueError('Claimed task total is required')
                values[field] = 'yes' if (Decimal(amount('sub'))+Decimal(amount('shipping')) == Decimal(amount('grand')) == Decimal(claimed_total)) else 'no'
            else: values[field] = amount({'subtotal':'sub','shipping_cost':'shipping','order_total':'grand'}[field])
        else: raise ValueError('Unsupported checkout value')
    return values


def wait_shipping_values(page, *, timeout=30000):
    """Native radio creation precedes Knockout price rendering; await all cells."""
    page.wait_for_function(r"""() => {
      const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      const rows=[...document.querySelectorAll('#co-shipping-method-form tr')]
        .filter(e=>visible(e)&&e.querySelector('input[type=radio]'));
      return rows.length>0 && rows.every(row=>{
        const cells=[...row.querySelectorAll('td')];
        return cells.length===4 && cells.slice(1).every(e=>visible(e)&&e.innerText.trim())
          && /\$[\d,]+\.\d{2}/.test(cells[1].innerText);
      }) && ![...document.querySelectorAll('.loading-mask')].some(visible);
    }""",timeout=timeout)


def ui_values(page, q, *, evidence_path=None):
    """Control-only native navigation to independently verify reference values."""
    validate(q)
    # These actions only run in CPU admission, never inside actor inference.
    from urllib.parse import urlsplit
    u = urlsplit(page.url); origin = u.scheme+'://'+u.netloc
    page.goto(origin+'/checkout/#shipping', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_function("""() => {
      const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      return [...document.querySelectorAll('.shipping-address-item.selected-item')].some(visible)
        && [...document.querySelectorAll('#co-shipping-method-form input[type=radio]')].some(visible)
        && ![...document.querySelectorAll('.loading-mask')].some(visible);
    }""", timeout=30000)
    wait_shipping_values(page)
    shipping = {'shipping_rows':page.locator('#co-shipping-method-form tr').evaluate_all('''es=>es.filter(e=>e.getClientRects().length).map(e=>({
      cells:[...e.querySelectorAll('td')].map(t=>t.innerText),inputs:[...e.querySelectorAll('input')].map(t=>({value:t.value,checked:t.checked,disabled:t.matches(':disabled')}))}))''')}
    identity = read_checkout_page(page)
    shipping['addresses']=identity['addresses']
    if evidence_path is not None:
        from .io_utils import atomic_write_json
        atomic_write_json(evidence_path, {'shipping':shipping, 'url':page.url})
    if str(identity['customer_id']) != str(q['customer_id']) or str(identity['quote_id']) != str(q['object_id']):
        raise ValueError('Wrong native checkout account/cart')
    # Never choose a task-specific method. The admitted baseline must provide a
    # native selection; an unselected or ambiguous baseline is not silently fixed.
    if page.locator('#co-shipping-method-form input[type=radio]:checked').count() != 1:
        raise ValueError('Native checkout did not select one shipping method')
    page.get_by_role('button',name='Next',exact=True).click(timeout=5000)
    page.locator('#payment .payment-method-title').first.wait_for(state='visible',timeout=30000)
    page.locator('.table-totals .grand.totals .price').wait_for(state='visible',timeout=30000)
    payment = {'summary_rows':page.locator('.table-totals tr').evaluate_all('''es=>es.filter(e=>e.getClientRects().length).map(e=>({
      class_name:e.className,label:e.querySelector('th')?.innerText,value:e.querySelector('td')?.innerText}))'''),
      'payment_labels':page.locator('#payment .payment-method-title').all_inner_texts()}
    if evidence_path is not None:
        atomic_write_json(evidence_path, {'shipping':shipping, 'payment':payment, 'url':page.url})
    return values_from_capture(shipping,payment,q['fields'],claimed_total=q.get('claimed_total'),from_shipping_method=q.get('from_shipping_method'))

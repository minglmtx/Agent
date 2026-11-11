"""Persisted quantity changes with non-quantity product options preserved."""
import json
from decimal import Decimal,InvalidOperation


def quantity(value):
    try:n=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError):return None
    return n if n.is_finite()and n>0 else None


def option_content(rows):
    if not isinstance(rows,list):raise ValueError('Missing persisted product-option evidence')
    normalized=[]
    for row in rows:
        row=dict(row)
        if row['code']=='info_buyRequest':
            try:value=json.loads(row['value'])
            except (ValueError,TypeError)as exc:raise ValueError('Unsupported native buy-request encoding')from exc
            if not isinstance(value,dict):raise ValueError('Native buy request must be an object')
            value.pop('qty',None)
            row['value']=value
        normalized.append(row)
    return normalized


def validate_initial(state):
    items=state['items']
    if not items or len({r['item_id']for r in items})!=len(items):raise ValueError('Unique initial cart items required')
    if any(quantity(r['qty'])is None for r in items):raise ValueError('Initial quantity must be finite and positive')
    option_content(state.get('item_options'))


def checks(initial,final):
    validate_initial(initial)
    before=initial['items'];after=final['items']
    if not isinstance(after,list)or len({r['item_id']for r in after})!=len(after):raise ValueError('Malformed saved cart items')
    # Price is derived by Magento (e.g. tier pricing) and need not remain equal
    # when quantity changes. Product identity and selected options must remain.
    keys=('item_id','product_id','parent_item_id','sku','name')
    identities=lambda rows:sorted(tuple(r.get(k)for k in keys)for r in rows)
    same=identities(before)==identities(after)
    old={r['item_id']:quantity(r['qty'])for r in before}
    positive=bool(after)and all(quantity(r['qty'])is not None for r in after)
    changed=same and positive and any(quantity(r['qty'])!=old[r['item_id']]for r in after)
    return {'cart_product_identities_preserved':same,
            'saved_quantities_valid':positive,
            'saved_quantity_changed':changed,
            'nonquantity_product_options_unchanged':option_content(initial.get('item_options'))==option_content(final.get('item_options'))}


FEEDBACK={
    'cart_product_identities_preserved':'The original cart products remain in the cart.',
    'saved_quantities_valid':'Saved cart quantities are finite and positive.',
    'saved_quantity_changed':'At least one original cart item has a different saved quantity.',
    'nonquantity_product_options_unchanged':'Product options other than quantity remain unchanged.',
}

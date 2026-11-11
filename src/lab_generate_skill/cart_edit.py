"""Versioned existing-item edits: saved quantities, options, or removals.

This predicate accepts combinations of these changes. It does not prescribe
which item or value the actor must choose. Adding new products is outside this
explicit derived-task boundary, rather than silently treated as equivalent.
"""
from .cart_quantity import quantity
from .cart_options import selections, allowed


def content(state, catalog):
    items=state.get('items');options=state.get('item_options')
    if not isinstance(items,list) or not isinstance(options,list):raise ValueError('Missing persisted cart edit evidence')
    if len({r['item_id']for r in items})!=len(items) or len({r['product_id']for r in items})!=len(items):
        raise ValueError('Ambiguous saved cart product identity')
    item_ids={r['item_id']for r in items}
    if any(r['item_id']not in item_ids for r in options):raise ValueError('Orphan saved option records')
    values={};valid=True
    for item in items:
        pid=str(item['product_id']);cat=catalog.get(pid)
        if cat is None:valid=False;continue
        rows=[r for r in options if r['item_id']==item['item_id']]
        if len({r['code']for r in rows})!=len(rows):raise ValueError('Duplicate saved option records')
        selected={}
        if cat['options']:
            try:selected=selections(state,item);valid &= allowed({'option_catalog':cat},selected)
            except ValueError:valid=False
        elif any(r['code'].startswith('option_')for r in rows):valid=False
        qty=quantity(item['qty'])
        valid &= qty is not None and item.get('parent_item_id')is None
        values[pid]={'name':item['name'],'quantity':qty,'options':selected}
    return values,bool(valid)


def validate_initial(state,spec):
    catalogs=state.get('option_catalogs')
    if not isinstance(catalogs,dict) or set(catalogs)!=set(map(str,spec['initial_product_ids'])):
        raise ValueError('Complete original-product option catalogs required')
    if any(any(r['type']not in ('radio','drop_down')for r in cat['options'])for cat in catalogs.values()):
        raise ValueError('Unvalidated custom option type')
    values,valid=content(state,catalogs)
    if not valid or not values or set(values)!=set(catalogs):raise ValueError('Invalid initial cart edit scope')


def checks(initial,final,spec):
    validate_initial(initial,spec)
    if final.get('option_catalogs')!=initial['option_catalogs']:raise ValueError('Product catalogs changed during attempt')
    before,_=content(initial,initial['option_catalogs'])
    after,valid=content(final,initial['option_catalogs'])
    identities=all(pid in before and row['name']==before[pid]['name']for pid,row in after.items())
    return {'saved_cart_edit_valid':valid and identities,
            'existing_cart_items_only':all(str(r['product_id'])in before for r in final['items']),
            'material_cart_edit_saved':valid and identities and before!=after}


FEEDBACK={'saved_cart_edit_valid':'Remaining cart products have valid saved quantities and catalog options.',
          'existing_cart_items_only':'The edit is limited to products in the initial cart.',
          'material_cart_edit_saved':'At least one original item was removed or has a changed saved quantity or option.'}

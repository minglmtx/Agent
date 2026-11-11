"""Persisted custom-option edits, separate from unsaved browser form state."""
from decimal import Decimal
from .site_database import select_rows


def catalog(site, product_id):
    ident = int(product_id)
    options = select_rows(site, 'SELECT o.option_id,o.type,o.is_require,t.title FROM catalog_product_option o '
        'JOIN catalog_product_option_title t ON t.option_id=o.option_id AND t.store_id=0 '
        f'WHERE o.product_id={ident} ORDER BY o.option_id')
    values = select_rows(site, 'SELECT v.option_id,v.option_type_id,t.title FROM catalog_product_option_type_value v '
        'JOIN catalog_product_option_type_title t ON t.option_type_id=v.option_type_id AND t.store_id=0 '
        'JOIN catalog_product_option o ON o.option_id=v.option_id '
        f'WHERE o.product_id={ident} ORDER BY v.option_id,v.option_type_id')
    return {'product_id': ident, 'options': options, 'values': values}


def target(state, spec):
    rows = [r for r in state['items'] if r['product_id'] == spec['product_id']]
    return rows[0] if len(rows) == 1 and rows[0]['name'] == spec['product_name'] else None


def selections(state, item):
    if not isinstance(state.get('item_options'), list): raise ValueError('Missing saved option evidence')
    rows = [r for r in state['item_options'] if r['item_id'] == item['item_id']]
    if len({r['code'] for r in rows}) != len(rows): raise ValueError('Duplicate saved option records')
    selected = {r['code'][7:]: str(r['value']) for r in rows if r['code'].startswith('option_') and r['code'] != 'option_ids'}
    ids = [r['value'] for r in rows if r['code'] == 'option_ids']
    if len(ids) != 1 or set(str(ids[0]).split(',')) != set(selected):
        raise ValueError('Saved option index inconsistent')
    return selected


def allowed(state, selected):
    cat = state.get('option_catalog')
    if not isinstance(cat, dict): raise ValueError('Missing catalog option definitions')
    options = {str(r['option_id']): r for r in cat['options']}
    if not options or any(r['type'] not in ('radio', 'drop_down') for r in options.values()):
        raise ValueError('Custom option kind requires separate validation')
    values = {str(r['option_id']): set() for r in cat['options']}
    for r in cat['values']: values[str(r['option_id'])].add(str(r['option_type_id']))
    return (set(selected) <= set(options) and all(k in selected for k,r in options.items() if r['is_require'])
            and all(v in values[k] for k,v in selected.items()))


def requested(state, spec):
    change = spec.get('requested_option')
    if change is None: return None
    if set(change) != {'name','from','to'}: raise ValueError('Explicit option name/from/to required')
    cat = state['option_catalog']
    options = [r for r in cat['options'] if r['title'] == change['name']]
    if len(options) != 1: raise ValueError('Requested option identity ambiguous')
    option = options[0]
    def ident(label):
        rows = [r for r in cat['values'] if r['option_id'] == option['option_id'] and r['title'] == label]
        if len(rows) != 1: raise ValueError('Requested option value missing or ambiguous')
        return str(rows[0]['option_type_id'])
    return str(option['option_id']), ident(change['from']), ident(change['to'])


def validate_initial(state, spec):
    item = target(state, spec)
    if item is None: raise ValueError('Unique original custom-option cart product required')
    selected = selections(state, item)
    if not allowed(state, selected): raise ValueError('Invalid initial custom options')
    req = requested(state, spec)
    if req and (selected.get(req[0]) != req[1] or req[1] == req[2]):
        raise ValueError('Original requested starting option not present')


def checks(initial, final, spec):
    validate_initial(initial, spec)
    before, after = target(initial, spec), target(final, spec)
    if not isinstance(final.get('item_options'), list): raise ValueError('Missing final saved option evidence')
    if final.get('option_catalog') != initial.get('option_catalog'):
        raise ValueError('Catalog option definitions changed during attempt')
    orig = selections(initial, before)
    try:
        now = selections(final, after) if after else {}
        valid = bool(after) and allowed(final, now)
    except ValueError:
        now, valid = {}, False
    req = requested(initial, spec)
    correct = (valid and now.get(req[0]) == req[2] and
               {k:v for k,v in now.items() if k != req[0]} == {k:v for k,v in orig.items() if k != req[0]}) if req else valid and now != orig
    other = lambda s: [r for r in s['items'] if r['product_id'] != spec['product_id']]
    # A deleted unrelated item fails the item comparison; stale/new unrelated
    # option rows also fail this independent check.
    other_opts = lambda s,t: [r for r in s['item_options'] if not t or r['item_id'] != t['item_id']]
    return {'target_option_saved': bool(correct), 'saved_option_values_valid': bool(valid),
            'target_quantity_preserved': bool(after) and Decimal(str(before['qty'])) == Decimal(str(after['qty'])),
            'unrelated_items_unchanged': other(initial) == other(final),
            'unrelated_options_unchanged': other_opts(initial, before) == other_opts(final, after)}


FEEDBACK = {'target_option_saved': 'The requested option change is saved on the intended cart product.',
            'saved_option_values_valid': 'Saved custom options are valid catalog choices.',
            'target_quantity_preserved': 'The target cart quantity is unchanged.'}

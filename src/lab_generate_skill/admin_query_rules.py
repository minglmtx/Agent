"""Typed, task-bound read-only queries; private references never enter actor prompts."""
import json
from decimal import Decimal, InvalidOperation

VERSION = 'admin-typed-query-v1'


def only(rows, reason):
    if len(rows) != 1:
        raise ValueError(reason)
    return rows[0]


def reference(spec, state, expected_id=None):
    if spec.get('product'):
        item = only(state['products'].get(spec['product'], []), 'product_missing_or_ambiguous')
        if expected_id is not None and int(item['entity_id']) != expected_id:
            raise ValueError('target_identity_changed')
        values = {}
        for field in spec['fields']:
            if field == 'sku':
                values[field] = item['sku']
            elif field == 'price':
                values[field] = item['attributes']['price']['0']
            elif field == 'stock_status':
                stock = only(item['stock_items'], 'stock_scope_missing_or_ambiguous')
                flag = str(stock['is_in_stock'])
                if flag not in ('0', '1'):
                    raise ValueError('invalid_stock_status')
                values[field] = 'In Stock' if flag == '1' else 'Out of Stock'
            else:
                raise ValueError('unsupported_product_field')
    else:
        item = only([o for o in state['query_orders'] if o['increment_id'] == spec['order_increment_id']],
                    'order_missing_or_ambiguous')
        if expected_id is not None and int(item['entity_id']) != expected_id:
            raise ValueError('target_identity_changed')
        values = {field: item[field] for field in spec['fields']}
    if any(v is None or v == '' for v in values.values()):
        raise ValueError('missing_reference')
    return int(item['entity_id']), values


def bind_query(row, state, spec):
    ident, values = reference(spec, state)
    b = {'spec':dict(spec), 'source_task_id':row['source_task_id'], 'goal':row['goal'],
         'kind':row['kind'], 'scope_id':0, 'status':'ready_for_single_attempt',
         'evaluator_version':VERSION, 'not_formal_training_admission':True,
         'query_reference':values, 'query_object_id':ident, 'answer_fields':list(spec['fields'])}
    if spec.get('product'):
        b.update(product_id=ident, product_name=spec['product'],
                 start_path=f'/catalog/product/edit/id/{ident}/store/0/')
    else:
        b.update(order_id=ident, order_increment_id=spec['order_increment_id'],
                 start_path=f'/sales/order/view/order_id/{ident}/')
    return b


def query_goal(binding):
    from .browser_prompt_contract import query_finish_instruction
    return (binding['goal'] + '\n' + query_finish_instruction(binding['spec']['fields'])
            + ' Use strings for SKU and currency, a number without a currency symbol for monetary '
            'values, and "In Stock" or "Out of Stock" for stock_status. Read the explicit Stock Status field; '
            'quantity alone does not determine this field. Do not modify records. This query is scored against '
            'the initial saved values; the final page must remain authenticated and valid.')


def same(field, actual, expected):
    if isinstance(actual, (bool, list, dict)) or actual is None:
        return False
    if field in ('price', 'grand_total'):
        try:
            a, b = Decimal(str(actual)), Decimal(str(expected))
            return a.is_finite() and b.is_finite() and a == b
        except InvalidOperation:
            return False
    if not isinstance(actual, str):
        return False
    # SKU is an identifier; stock labels and currency tolerate casing only.
    return actual.strip() == str(expected) if field == 'sku' else actual.strip().casefold() == str(expected).casefold()


def parse_answer(answer):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('duplicate_answer_key')
            obj[key] = value
        return obj
    value = json.loads(answer, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError('answer_not_object')
    return value


def query_checks(binding, before, after, answer):
    spec = binding['spec']; ident = binding['query_object_id']
    _, initial = reference(spec, before, ident)
    _, final = reference(spec, after, ident)
    if initial != binding['query_reference']:
        raise ValueError('binding_reference_changed')
    checks = {'requested_values_unchanged':initial == final}
    try:
        value = parse_answer(answer)
    except (ValueError, TypeError):
        checks['answer_schema'] = False
        return checks
    checks['answer_schema'] = set(value) == set(initial)
    for field, expected in initial.items():
        checks['answer_' + field] = same(field, value.get(field), expected)
    return checks

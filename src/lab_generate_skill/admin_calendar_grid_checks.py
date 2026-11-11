"""Nested provider filter checks for the declared calendar operation only."""
from .admin_grid_operation import PROTOCOL

def provider_filter_params(filters):
    """Encode native nested filter values like the corresponding HTTP form keys."""
    if not isinstance(filters, dict):
        raise ValueError('grid_filter_object_required')
    result = {}
    def visit(prefix, value):
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str) or not key or '[' in key or ']' in key:
                    raise ValueError('ambiguous_grid_filter_key')
                visit(prefix + '[' + key + ']', item)
        elif isinstance(value, (list, tuple, set)):
            raise ValueError('unsupported_grid_filter_sequence')
        elif value not in (None, ''):
            result[prefix] = [str(value)]
    for key, value in filters.items():
        if not isinstance(key, str) or not key or '[' in key or ']' in key:
            raise ValueError('ambiguous_grid_filter_key')
        if key != 'placeholder':
            visit('filters[' + key + ']', value)
    return result

def checks(spec, evidence):
    if not evidence or evidence.get('protocol') != PROTOCOL or evidence.get('probe_error'):
        raise ValueError('grid_operation_evidence_unavailable')
    provider = evidence['provider']
    expected = {k: [str(v)] for k, v in spec['request_params'].items()}
    receipts = evidence.get('receipts', [])
    latest = receipts[-1] if receipts else {}
    params = provider.get('params', {})
    current = {'search': [str(params['search'])]} if params.get('search') not in (None, '') else {}
    current.update(provider_filter_params(params.get('filters', {})))
    submitted = {k: v for k, v in latest.get('params', {}).items()
                 if k != 'filters[placeholder]' and v != ['']}
    return {
        'required_grid_request_completed': bool(latest.get('response_valid')),
        'requested_grid_parameters_submitted': submitted == expected,
        'requested_grid_parameters_current': current == expected,
        'grid_response_applied': bool(latest) and not provider.get('loading')
            and not provider.get('last_error')
            and provider.get('row_ids') == latest.get('row_ids')
            and provider.get('total_records') == latest.get('total_records'),
    }

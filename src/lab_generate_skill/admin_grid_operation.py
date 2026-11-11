"""Evidence for explicitly requested grid operations, separate from answer accuracy.

Read-only observers; never fill filters, click controls, or prescribe actor steps.
Only tasks declaring required_grid_operation use this protocol.
"""
from urllib.parse import parse_qs, urlsplit

PROTOCOL = 'admin-grid-operation-v1'


def request_scope(url, post_data, spec, netloc):
    parsed = urlsplit(url)
    # Magento may append its authentication key to the native render route.
    path = parsed.path.rstrip('/')
    route = spec['render_path'].rstrip('/')
    if parsed.netloc != netloc or not (path == route or path.startswith(route + '/key/')):
        return None
    params = parse_qs(parsed.query, keep_blank_values=True)
    for key, values in parse_qs(post_data or '', keep_blank_values=True).items():
        if key in params and params[key] != values:
            return None
        params[key] = values
    if params.get('namespace') != [spec['namespace']]:
        return None
    return {k: v for k, v in params.items() if k == 'search' or k.startswith('filters[')}


def install(page, binding):
    spec = binding['spec'].get('required_grid_operation')
    if not spec:
        return
    page._admin_grid_operation = spec
    page._admin_grid_receipts = []

    def completed(request):
        params = request_scope(request.url, request.post_data, spec, binding['site_netloc'])
        if params is None:
            return
        receipt = {'params': params, 'response_valid': False}
        # Even a later failed/wrong-filter request supersedes earlier success.
        page._admin_grid_receipts.append(receipt)
        try:
            response = request.response()
            receipt['status'] = response.status if response else None
            if response is None or response.status != 200:
                return
            data = response.json()
            receipt['response_valid'] = (isinstance(data, dict)
                and isinstance(data.get('items'), list)
                and isinstance(data.get('totalRecords'), int)
                and not isinstance(data['totalRecords'], bool)
                and data['totalRecords'] >= len(data['items'])
                and not data.get('error'))
            if receipt['response_valid']:
                receipt['total_records'] = data['totalRecords']
                receipt['row_ids'] = [str(r.get('entity_id')) for r in data['items']]
        except Exception as exc:
            receipt['response_valid'] = False
            receipt['error'] = type(exc).__name__
    page.on('requestfinished', completed)


def probe(page):
    spec = getattr(page, '_admin_grid_operation', None)
    if not spec:
        return None
    result = {'protocol': PROTOCOL, 'receipts': list(page._admin_grid_receipts)}
    try:
        result['provider'] = page.evaluate('''name => {
          const p = require('uiRegistry').get(name);
          if (!p) throw new Error('grid_provider_missing');
          const unwrap = x => typeof x === 'function' ? x() : x;
          const data = unwrap(p.data) || {};
          return {params: unwrap(p.params) || {},
            row_ids: (data.items || []).map(x => String(x.entity_id)),
            total_records: data.totalRecords,
            loading: !!unwrap(p.loading) || [...document.querySelectorAll('.admin__data-grid-loading-mask')]
              .some(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden'
                && getComputedStyle(e).display !== 'none'),
            last_error: !!unwrap(p.lastError)};
        }''', spec['provider'])
    except Exception as exc:
        result['probe_error'] = type(exc).__name__
        result['probe_error_detail'] = str(exc).split('\n')[0][:300]
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
    for key, value in params.get('filters', {}).items():
        if key != 'placeholder' and value not in (None, ''):
            current['filters[' + key + ']'] = [str(value)]
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

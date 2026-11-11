"""Private complete native category reference, with diagnostics before rejection.

This optional reader is not integrated into a live probe or actor runtime. The
actual native first page provides the result count and customer group. A fresh
PHP process configures that complete window before any collection render, keeps
native filters/final prices, and returns every row. No product is dropped and no
regular database price substitutes for the native final price.
"""
import hashlib
import json
import re
import subprocess
from decimal import Decimal
from pathlib import Path
import time
from urllib.parse import urlsplit

from .io_utils import atomic_write_json
from .shopping_collection_reference import native_collection, validate_scope

VERSION = 'shopping-complete-native-category-v1'
NATIVE_SOURCES = {
    'module-catalog/Model/Layer.php',
    'module-catalog-search/Model/Layer/Filter/Category.php',
    'module-catalog-search/Model/Layer/Filter/Price.php',
    'module-catalog/Block/Product/ProductList/Toolbar.php',
    'module-catalog-search/Model/ResourceModel/Fulltext/Collection.php',
    'module-elasticsearch/Model/ResourceModel/Fulltext/Collection/SearchCriteriaResolver.php',
    'module-elasticsearch/Model/ResourceModel/Fulltext/Collection/SearchResultApplier.php',
    'framework/Data/Collection.php',
    'framework/Data/Collection/AbstractDb.php',
}


def _rows(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError('Native category records missing')
    ids = set()
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'id', 'name', 'price'}
                or type(row['id']) is not int or row['id'] <= 0 or row['id'] in ids
                or not isinstance(row['name'], str) or not row['name'].strip()
                or not isinstance(row['price'], str) or not re.fullmatch(r'\d+(?:\.\d+)?', row['price'])):
            raise ValueError('Native product identity/name/final price incomplete or duplicated')
        ids.add(row['id'])
    return [(r['id'], r['name'], Decimal(r['price'])) for r in rows]


def validate_complete_category(data, first_page, scope):
    """Exact independent count, scope, public first-page identity and final prices."""
    validate_scope(scope)
    if scope['kind'] != 'category':
        raise ValueError('Complete native category scope required')
    if not isinstance(data, dict) or not isinstance(first_page, dict):
        raise ValueError('Complete native output and native first page required')
    total = first_page.get('total')
    if (type(total) is not int or not 0 < total <= 10000
            or data.get('reader_version') != VERSION or data.get('status') != 'complete'
            or type(data.get('total')) is not int or data['total'] != total
            or type(data.get('page')) is not int or data['page'] != 1
            or type(first_page.get('page')) is not int or first_page['page'] != 1
            or type(data.get('limit')) is not int or data['limit'] != total
            or data.get('scope') != scope['path'] or first_page.get('scope') != scope['path']
            or data.get('category') != first_page.get('category')
            or not isinstance(data.get('category'), dict)
            or type(data['category'].get('id')) is not int or data['category']['id'] != scope['category_id']
            or data['category'].get('active') is not True
            or type(data.get('account_group')) is not int or data['account_group'] < 0
            or type(first_page.get('account_group')) is not int or data['account_group'] != first_page['account_group']
            or not isinstance(data.get('order'), str) or not data['order'] or data['order'] != first_page.get('order')
            or data.get('direction') not in ('asc', 'desc') or data['direction'] != first_page.get('direction')
            or data.get('facets') != first_page.get('facets')
            or data.get('active_filters') != first_page.get('active_filters')):
        raise ValueError('Complete native collection scope/count/customer/filters changed')
    full = _rows(data.get('products'))
    first = _rows(first_page.get('products'))
    if len(full) != total or len(first) > total or full[:len(first)] != first:
        raise ValueError('Complete native rows or first-page identities/final prices differ')
    diagnostics = data.get('diagnostics')
    if not isinstance(diagnostics, dict):
        raise ValueError('Complete native diagnostics unavailable')
    before = diagnostics.get('before_first_render')
    after = diagnostics.get('after_iteration')
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError('Native first-render/iteration diagnostics unavailable')
    if (before.get('loaded') is not False or before.get('filters_rendered') is not False
            or type(before.get('page')) is not int or before['page'] != 1
            or type(before.get('limit')) is not int or before['limit'] != total
            or any(type(after.get(k)) is not int or after[k] != total for k in
                   ('expected_total', 'native_total_before', 'native_total_after', 'returned_rows', 'distinct_ids'))
            or not isinstance(after.get('sql'), str) or not after['sql'].strip()
            or not isinstance(data.get('source_hashes'), dict) or set(data['source_hashes']) != NATIVE_SOURCES
            or any(not isinstance(h, str) or not re.fullmatch(r'[0-9a-f]{64}', h) for h in data['source_hashes'].values())):
        raise ValueError('Complete first-render provenance or native SQL coverage unavailable')
    first_hashes = first_page.get('source_hashes')
    common = {'module-catalog/Model/Layer.php', 'module-catalog-search/Model/Layer/Filter/Category.php',
              'module-catalog-search/Model/Layer/Filter/Price.php', 'module-catalog/Block/Product/ProductList/Toolbar.php'}
    if (not isinstance(first_hashes, dict) or not common <= set(first_hashes)
            or any(first_hashes[k] != data['source_hashes'][k] for k in NATIVE_SOURCES.intersection(first_hashes))):
        raise ValueError('Installed native source changed between complete and first-page queries')
    return data


def complete_native_category(site, scope, username, *, capture_path):
    """Fresh native queries; save actual output/SQL/partial state before checks.

    capture_path is mandatory private diagnostic storage. First-page display and
    price-box comparisons remain the caller's responsibility using actual UI.
    """
    path = Path(capture_path)
    if path.exists():
        raise ValueError('Preserve previous native diagnostics; use a new capture path')
    validate_scope(scope)
    if scope['kind'] != 'category':
        raise ValueError('Complete category reader does not silently alter other scopes')
    first_page = native_collection(site, scope, username)
    total = first_page['total']
    if type(total) is not int or not 0 < total <= 10000:
        atomic_write_json(path, {'version': VERSION, 'status': 'unsupported_native_window', 'native_first_page': first_page})
        raise ValueError('Native category exceeds this complete-window implementation')
    args = dict(scope, host=urlsplit(site.url).netloc,
                customer_group_id=first_page['account_group'], expected_total=total)
    php = Path(__file__).with_name('shopping_complete_native_category.php')
    code = php.read_text().removeprefix('<?php')
    start = time.monotonic()
    try:
        result = site.command(['php', '-d', 'memory_limit=1024M', '-r', code, json.dumps(args)],
                              capture_output=True, text=True, timeout=90)
    except subprocess.CalledProcessError as error:
        # The common site.command uses check=True. Native partial/error JSON is
        # still real evidence and must be saved before rejecting exit status.
        result = subprocess.CompletedProcess([], error.returncode,
            error.stdout or '', error.stderr or '')
    except Exception as error:
        partial = getattr(error, 'stdout', None) or getattr(error, 'output', None) or ''
        if isinstance(partial, bytes):
            partial = partial.decode('utf-8', errors='replace')
        try:
            partial_json = json.loads(partial)
        except (ValueError, TypeError):
            partial_json = None
        atomic_write_json(path, {'version': VERSION, 'status': 'native_command_error',
            'native_first_page': first_page, 'exception_class': type(error).__name__,
            'native_partial_output': partial_json, 'stdout_bytes': len(partial.encode()),
            'stdout_sha256': hashlib.sha256(partial.encode()).hexdigest(), 'seconds': time.monotonic() - start})
        raise
    if isinstance(result.stdout, bytes):
        result.stdout = result.stdout.decode('utf-8', errors='replace')
    if isinstance(result.stderr, bytes):
        result.stderr = result.stderr.decode('utf-8', errors='replace')
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError):
        atomic_write_json(path, {'version': VERSION, 'status': 'native_json_error',
            'native_first_page': first_page, 'returncode': result.returncode,
            'stdout_sha256': hashlib.sha256(result.stdout.encode()).hexdigest(),
            'stdout_bytes': len(result.stdout.encode()), 'seconds': time.monotonic() - start})
        raise ValueError('Complete native category JSON unavailable') from None
    atomic_write_json(path, {'version': VERSION, 'native_first_page': first_page,
        'native_output': data, 'returncode': result.returncode, 'reader_sha256': hashlib.sha256(php.read_bytes()).hexdigest(),
        'stderr_sha256': hashlib.sha256(result.stderr.encode()).hexdigest(),
        'stderr_bytes': len(result.stderr.encode()), 'seconds': time.monotonic() - start})
    if result.returncode != 0:
        raise ValueError('Complete native category query failed; private diagnostics saved')
    validate_complete_category(data, first_page, scope)
    return data, first_page

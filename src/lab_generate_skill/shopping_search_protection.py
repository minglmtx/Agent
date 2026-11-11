"""Bind native full-row search admissions to the same episode fingerprint.

Legacy admissions retain their selected-record fingerprint. New proofs marked
as full22 require the exact private native protection scope used by controls;
the two algorithms are never substituted for one another.
"""
import hashlib
import json
from pathlib import Path
import re

from .io_utils import atomic_write_json

VERSION = 'shopping-search-native-protection-v1'
SNAPSHOT_VERSION = 'shopping-seven-protected-full-rows-v1'
TABLES = frozenset((
    'customer_entity', 'customer_entity_datetime', 'customer_entity_decimal',
    'customer_entity_int', 'customer_entity_text', 'customer_entity_varchar',
    'customer_address_entity', 'customer_address_entity_datetime',
    'customer_address_entity_decimal', 'customer_address_entity_int',
    'customer_address_entity_text', 'customer_address_entity_varchar',
    'sales_order', 'sales_order_item', 'sales_order_address', 'sales_order_payment',
    'quote_item', 'quote_item_option', 'salesrule', 'salesrule_coupon',
    'salesrule_customer_group', 'salesrule_website',
))


def uses_full_protection(contract, proof):
    """Choose only the explicitly recorded search-family proof algorithm."""
    if contract.get('domain') != 'shopping' or not contract.get('search'):
        return False
    cycles = proof.get('cycles', [])
    if not isinstance(cycles, list):
        raise ValueError('Invalid native search protection cycles')
    marked = 'full22_protection_equal' in proof or any(
        'full22_table_fingerprint' in row for row in cycles if isinstance(row, dict)
    )
    if not marked:
        return False
    if proof.get('full22_protection_equal') is not True or len(cycles) != 2:
        raise ValueError('Incomplete native full22 search protection proof')
    for row in cycles:
        if not isinstance(row, dict) or row.get('full22_table_fingerprint') is not True:
            raise ValueError('Mixed native search fingerprint algorithms')
        value = row.get('initial_fingerprint')
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value) or value != row.get('final_fingerprint'):
            raise ValueError('Incomplete native full22 search protection fingerprint')
    return True


def validate_snapshot(value):
    """Reject incomplete coverage and undeclared mutable columns."""
    if not isinstance(value, dict) or value.get('version') != SNAPSHOT_VERSION or value.get('statement_budget_seconds') != 20:
        raise ValueError('Invalid native full22 search protection snapshot')
    tables = value.get('tables')
    if not isinstance(tables, dict) or set(tables) != TABLES:
        raise ValueError('Incomplete native full22 search protection tables')
    for table, row in tables.items():
        if not isinstance(row, dict) or type(row.get('rows')) is not int or row['rows'] < 0 or type(row.get('chunks')) is not int or row['chunks'] < 1:
            raise ValueError('Invalid native full22 table coverage')
        if not isinstance(row.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', row['sha256']):
            raise ValueError('Invalid native full22 table digest')
        columns = row.get('columns')
        keys = row.get('primary_key')
        if not isinstance(columns, list) or not columns or not all(isinstance(x, str) and x for x in columns) or len(columns) != len(set(columns)):
            raise ValueError('Invalid native full22 column coverage')
        if not isinstance(keys, list) or not keys or not all(isinstance(x, str) and x for x in keys) or len(keys) != len(set(keys)) or not set(keys) <= set(columns):
            raise ValueError('Invalid native full22 primary key coverage')
        if row.get('ignored_columns') != (['updated_at'] if table == 'quote_item' else []):
            raise ValueError('Undeclared native full22 mutable columns')
    return value


def snapshot_fingerprint(value):
    validate_snapshot(value)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def protected_snapshot(site):
    php = Path(__file__).with_name('shopping_seven_protection.php')
    result = site.command(['php', '-r', php.read_text().removeprefix('<?php')],
                          capture_output=True, text=True, timeout=180)
    return validate_snapshot(json.loads(result.stdout))


def episode_fingerprint(site, contract, proof, directory, *, phase):
    """Return and record the before/after fingerprint for this proof family."""
    if phase not in ('before', 'after'):
        raise ValueError('Expected an episode before/after protection phase')
    from . import reddit_navigation_protection as reddit_navigation
    if reddit_navigation.enabled(contract,proof):
        return reddit_navigation.capture(site,contract,proof,directory,phase)
    from . import reddit_query_protection as reddit_query
    if reddit_query.enabled(contract,proof):
        return reddit_query.capture(site,contract,proof,directory,phase)
    if uses_full_protection(contract, proof):
        value = protected_snapshot(site)
        atomic_write_json(Path(directory) / ('search-protected-' + phase + '.json'), value)
        # The full22 admission scope does not include catalog_product_entity.
        # Preserve the original selected catalog/customer/order guard separately
        # instead of replacing it with the more detailed account/order snapshot.
        selected = site.fingerprint(include_orders=False) if contract.get('order') else site.fingerprint()
        atomic_write_json(Path(directory) / ('search-selected-' + phase + '.json'),
                          {'version': 'shopping-search-selected-integrity-v1', 'sha256': selected})
        return snapshot_fingerprint(value)
    if contract.get('domain') == 'gitlab':
        from .gitlab_site import IsolatedGitlabSite
        if isinstance(site, IsolatedGitlabSite):
            # Private episode evidence, never an Actor observation or feedback.
            return site.fingerprint(evidence_path=Path(directory) / ('selected-projects-' + phase + '.csv'))
    return site.fingerprint(include_orders=False) if contract.get('order') else site.fingerprint()


def search_selected_integrity(contract, proof, directory):
    """Retain the old selected-table guard for new full22 search episodes."""
    from . import reddit_navigation_protection as reddit_navigation
    if reddit_navigation.enabled(contract,proof):return reddit_navigation.selected_integrity(directory)
    from . import reddit_query_protection as reddit_query
    if reddit_query.enabled(contract,proof):return reddit_query.selected_integrity(directory)
    if not uses_full_protection(contract, proof):
        return True
    records = []
    for phase in ('before', 'after'):
        path = Path(directory) / ('search-selected-' + phase + '.json')
        if not path.is_file():
            return False
        try:
            record = json.loads(path.read_text())
        except (ValueError, OSError):
            return False
        if not isinstance(record, dict) or record.get('version') != 'shopping-search-selected-integrity-v1':
            return False
        value = record.get('sha256')
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
            return False
        records.append(value)
    return records[0] == records[1]

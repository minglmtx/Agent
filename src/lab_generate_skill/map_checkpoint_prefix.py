"""Reuse committed range proofs only with their exact closed database checkpoint.

This consumes trusted builder receipts, never observations or actor messages.
Unrecorded final transactions are deliberately rechecked on resume.
"""
import hashlib
import json
from pathlib import Path
from .map_current_tables import bounds, projection


def load_prefixes(path, expected_sha, checkpoint, checkpoint_sha):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('Changed range proof')
    proof = json.loads(raw)
    if (proof['checkpoint_sha256'] != checkpoint_sha
            or Path(proof['checkpoint']).resolve() != Path(checkpoint).resolve()
            or hashlib.sha256(Path(checkpoint).read_bytes()).hexdigest() != checkpoint_sha):
        raise ValueError('Range proof belongs to a different database checkpoint')
    receipt = json.loads(Path(checkpoint).read_text())
    if receipt['version'] != 'map28-native-pg11-closed-checkpoint-v2':
        raise ValueError('Clean closed checkpoint required')
    result = {}
    for item in proof['pieces']:
        name, lo, hi = item['piece']; projection(name); bounds(lo, hi)
        key = (name, lo, hi)
        if key in result:
            raise ValueError('Duplicate piece proof')
        data = Path(item['journal']).read_bytes()
        if hashlib.sha256(data).hexdigest() != item['journal_sha256']:
            raise ValueError('Changed committed range journal')
        cursor, total, count = lo, 0, 0
        for line in data.splitlines():
            row = json.loads(line)
            lower, upper = row['lower'], row['upper']; bounds(lower, upper)
            if (row['table'] != name or lower < cursor or upper > hi
                    or row.get('exact_equal') is not True or row.get('committed') is not True
                    or type(row['rows']) is not int or row['rows'] < 0):
                raise ValueError('Invalid, overlapping or uncommitted range proof')
            # Gaps were shown empty by the original union-minimum query.
            cursor = upper; total += row['rows']; count += 1
        result[key] = {'cursor': cursor, 'rows': total, 'ranges': count,
                       'journal_sha256': item['journal_sha256']}
    return result


def combine(prefix, result, lower_bound):
    if prefix is None:
        return result
    if result['lower_bound'] != prefix['cursor']:
        raise ValueError('Resumed interval does not follow the verified prefix')
    return {**result, 'lower_bound': lower_bound,
            'rows': prefix['rows'] + result['rows'],
            'ranges': prefix['ranges'] + result['ranges'],
            'reused_prefix': prefix,
            'validation': 'checkpoint_bound_prefix_plus_exact_remaining_ranges'}


def embedded_prefixes(receipt):
    """Prefixes are bound by the hash of their containing closed receipt."""
    items = receipt.get('verified_range_prefixes', [])
    if not isinstance(items, list):
        raise ValueError('Range prefixes must be a list')
    if items and receipt.get('version') != 'map28-native-pg11-closed-checkpoint-v2':
        raise ValueError('Closed database checkpoint required')
    result = {}
    for item in items:
        name, lo, hi = item['piece']; projection(name); bounds(lo, hi)
        cursor, rows, ranges = (item[k] for k in ('cursor', 'rows', 'ranges'))
        if (any(type(x) is not int for x in (cursor, rows, ranges))
                or not lo <= cursor <= hi or rows < 0 or ranges < 0
                or item.get('committed_and_exact') is not True):
            raise ValueError('Invalid committed prefix')
        for other, a, b in result:
            if other == name and max(lo, a) < min(hi, b):
                raise ValueError('Overlapping checkpoint pieces')
        result[(name, lo, hi)] = dict(cursor=cursor, rows=rows, ranges=ranges)
    return result


def closed_prefixes(inherited, journals):
    """Call only after all DB workers have closed their committed journals.

    An unjournaled transaction is rechecked; no database work is skipped merely
    because it appears in a progress counter or in a failed SQL log.
    """
    result = {piece: dict(value) for piece, value in inherited.items()}
    for piece, path in journals.items():
        name, lo, hi = piece; projection(name); bounds(lo, hi)
        value = result.setdefault(piece, dict(cursor=lo, rows=0, ranges=0))
        with Path(path).open() as stream:
            for line in stream:
                row = json.loads(line)
                lower, upper = row['lower'], row['upper']; bounds(lower, upper)
                if (row['table'] != name or lower < value['cursor'] or upper > hi
                        or row.get('committed') is not True or row.get('exact_equal') is not True
                        or type(row['rows']) is not int or row['rows'] < 0):
                    raise ValueError('Journal does not extend its committed checkpoint prefix')
                value.update(cursor=upper, rows=value['rows'] + row['rows'],
                             ranges=value['ranges'] + 1)
    items = [dict(piece=list(piece), cursor=v['cursor'], rows=v['rows'],
                  ranges=v['ranges'], committed_and_exact=True)
             for piece, v in sorted(result.items())]
    embedded_prefixes(dict(version='map28-native-pg11-closed-checkpoint-v2',
                          verified_range_prefixes=items))
    return items

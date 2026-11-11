"""Reported charges, reconciled charges and unconfirmed reservations stay separate."""
import json
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING

from .io_utils import atomic_write_json, iter_jsonl


def valid_cost(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def attempt_key(row):
    return row['generation_id'], row.get('attempt', 1)


def no_charge(row):
    return (row.get('billing_status') == 'not_sent'
            or row.get('parse_error') == 'RateLimitError: HTTP 429'
            or row.get('api_error_code') == 429)


def billing_records(directory):
    ledger = directory / 'raw_generations.jsonl'
    rows = list(iter_jsonl(ledger)) if ledger.exists() else []
    by_key = {attempt_key(row): row for row in rows}
    if len(by_key) != len(rows):
        raise ValueError('Duplicate billing attempt')
    tables = []
    for name, field in [('billing_reservations.json', 'reserved_usd'),
                        ('billing_reconciliations.json', 'actual_cost_usd')]:
        path = directory / name
        entries = json.loads(path.read_text()) if path.exists() else []
        table = {}
        for entry in entries:
            key = attempt_key(entry)
            amount = entry[field]
            if key not in by_key or key in table or not valid_cost(amount):
                raise ValueError('Invalid or duplicate billing adjustment')
            if field == 'actual_cost_usd' and valid_cost(by_key[key].get('cost')):
                raise ValueError('Cannot replace an already reported charge')
            table[key] = entry
        tables.append(table)
    return rows, *tables


def unresolved_rows(rows, reconciled):
    return [row for row in rows if not valid_cost(row.get('cost'))
            and not no_charge(row) and attempt_key(row) not in reconciled]


def cost_state(directory):
    rows, reserves, reconciled = billing_records(directory)
    spent = sum(row['cost'] for row in rows if valid_cost(row.get('cost')))
    settled = sum(entry['actual_cost_usd'] for entry in reconciled.values())
    pending = unresolved_rows(rows, reconciled)
    reserved = sum(reserves[attempt_key(row)]['reserved_usd'] for row in pending
                   if attempt_key(row) in reserves)
    automatic = sum(reserves.get(attempt_key(row), {}).get('source') == 'bounded_unknown_policy'
                    for row in pending)
    unreserved = sum(attempt_key(row) not in reserves for row in pending)
    return dict(reported_cost_usd=spent, reconciled_cost_usd=settled,
                reserved_unconfirmed_cost_usd=reserved,
                budget_accounted_usd=spent + settled + reserved,
                unresolved_cost_calls=len(pending), auto_reserved_unknown_calls=automatic,
                unreserved_unknown_calls=unreserved)


def reservation_estimate(model_info, extractor):
    """Text-only estimate using full context and the highest advertised pricing tier.

    The routing max_price is NOT assumed to cap long-context surcharges. Include
    cache-write prices conservatively. This is a planning reserve, not a receipt.
    No web-search, image, tool or other paid add-on is sent by this extractor.
    """
    context = model_info.get('context_length')
    pricing = model_info.get('pricing')
    caps = extractor.provider_max_price or {}
    if not isinstance(context, int) or context <= 0 or not isinstance(pricing, dict):
        raise ValueError('Cannot estimate unknown fees without context and catalog pricing')
    if not {'prompt', 'completion'} <= caps.keys():
        raise ValueError('Unknown-fee policy requires explicit prompt/completion price caps')
    tiers = [pricing] + pricing.get('overrides', [])
    def rates(fields):
        values = []
        for tier in tiers:
            for key in fields:
                if key in tier:
                    value = Decimal(str(tier[key]))
                    if not value.is_finite() or value < 0:
                        raise ValueError('Invalid catalog price')
                    values.append(value)
        return values
    if not rates(['prompt']) or not rates(['completion']):
        raise ValueError('Missing catalog token prices')
    prompt = max(rates(['prompt', 'input_cache_read', 'input_cache_write'])
                 + [Decimal(str(caps['prompt'])) / 1000000])
    completion = max(rates(['completion']) + [Decimal(str(caps['completion'])) / 1000000])
    per_request = max(rates(['request']) + [Decimal(str(caps.get('request', 0)))])
    amount = context * prompt + extractor.max_new_tokens * completion + per_request
    if not amount.is_finite() or amount <= 0:
        raise ValueError('Invalid reservation estimate')
    return dict(reserved_usd=float(amount.quantize(Decimal('0.01'), rounding=ROUND_CEILING)),
                context_length=context, max_output_tokens=extractor.max_new_tokens,
                input_usd_per_token=str(prompt), output_usd_per_token=str(completion),
                request_usd=str(per_request), model=model_info['model'],
                calculated_at=datetime.now(timezone.utc).isoformat(),
                note='Conservative current-catalog planning estimate including long-context/cache tiers; not an actual charge or historical billing guarantee.')


def reserve_unknown_requests(directory, *, limit, estimate):
    """Legacy explicit reservations remain; new automatic slots persist across restarts."""
    rows, reserves, reconciled = billing_records(directory)
    pending = unresolved_rows(rows, reconciled)
    eligible = [row for row in pending if attempt_key(row) not in reserves
                or reserves[attempt_key(row)].get('source') == 'bounded_unknown_policy']
    if estimate is not None and len(eligible) <= limit:
        changed = False
        for row in eligible:
            key = attempt_key(row)
            existing = reserves.get(key)
            # Never silently lower an existing reserve after a price change.
            if existing and existing['reserved_usd'] >= estimate['reserved_usd']:
                continue
            reserves[key] = dict(generation_id=key[0], attempt=key[1],
                                 reserved_usd=estimate['reserved_usd'],
                                 source='bounded_unknown_policy', status='unconfirmed',
                                 basis=estimate)
            changed = True
        if changed:
            atomic_write_json(directory / 'billing_reservations.json', list(reserves.values()))
    audit = []
    for row in pending:
        reservation = reserves.get(attempt_key(row))
        audit.append({key: row.get(key) for key in
                      ('generation_id', 'attempt', 'trace_ids', 'generated_at', 'parse_error',
                       'provider_response_id', 'provider_request_id', 'error_diagnostics', 'elapsed_seconds')})
        audit[-1].update(retry_blocked=True, reserved_usd=reservation['reserved_usd'] if reservation else None)
    atomic_write_json(directory / 'unknown_cost_requests.json', audit)
    return cost_state(directory), {row['generation_id'] for row in pending}, len(eligible) > limit

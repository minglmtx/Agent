"""Wall-time based affordability check for exact native database recovery.

Row estimates affect scheduling only, never equality or table completeness.
Slow work must not escape the check by failing to reach a row-count threshold.
"""
import math


def throughput_decision(*, estimated_rows, rows, ranges, elapsed, remaining):
    values = (estimated_rows, rows, ranges, elapsed, remaining)
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('Finite nonnegative work measurements required')
    if elapsed < 120 or (ranges < 4 and elapsed < 300):
        return {'measured': False, 'stop': False}
    if estimated_rows <= 0 or rows <= 0:
        return {'measured': True, 'stop': True,
                'reason': 'No usable total-work estimate or measured progress'}
    rate = rows / elapsed  # Actual batch wall time includes scheduling/lookup.
    estimate = 1.3 * max(0, estimated_rows - rows) / rate
    return {'measured': True, 'stop': estimate > remaining,
            'rows_per_wall_second': rate,
            'estimated_remaining_seconds_with_30_percent_margin': estimate,
            'reason': 'Projected work exceeds remaining budget' if estimate > remaining else None}

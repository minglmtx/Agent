"""Public count text with explicit precision; rounded displays are not answers.

Only ``integer_count`` returns an exact integer. ``parse_public_count`` retains
both the original text and an ``exact`` tag, so presentation-unit conversions
cannot silently become oracle values for counts, thresholds, or ties.
"""
from decimal import Decimal, localcontext
import re


EXACT_COUNT = re.compile(r'(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)', re.ASCII)
ROUNDED_COUNT = re.compile(r'((?:0|[1-9]\d*)(?:\.\d+)?)([kKmMbB])', re.ASCII)
UNIT_MULTIPLIERS = {'k': 1000, 'm': 1000000, 'b': 1000000000}


def integer_count(text):
    """Parse a complete nonnegative integer with valid thousands grouping."""
    if not isinstance(text, str) or not EXACT_COUNT.fullmatch(text):
        raise ValueError('Not an exact public count')
    return int(text.replace(',', ''))


def parse_public_count(text):
    """Return original display, Decimal/int value, and whether it is exact.

    A suffix-bearing value remains approximate even if multiplying its mantissa
    produces an integer. Native formatting and rounding precision are unknown;
    callers must obtain independent public evidence before exact comparisons.
    """
    try:
        return {'display': text, 'value': integer_count(text), 'exact': True}
    except ValueError:
        match = ROUNDED_COUNT.fullmatch(text) if isinstance(text, str) else None
        if match is None:
            raise ValueError('Unrecognized public count representation') from None
    mantissa, unit = match.groups()
    # Keep all displayed decimal digits; avoid float rounding or the ambient
    # Decimal precision truncating a long, otherwise valid public label.
    with localcontext() as context:
        context.prec = max(28, len(mantissa.replace('.', '')) + 9)
        value = Decimal(mantissa) * UNIT_MULTIPLIERS[unit.lower()]
    return {'display': text, 'value': value, 'exact': False}

"""Explicit initial-scale derivatives; no actor-selected value defines a target."""
from decimal import Decimal, InvalidOperation


def multiplier(candidate):
    spec = candidate['candidate_completion']
    scope = spec.get('reference_scope')
    if scope == 'initial_view_default_native_share_form':
        if 'initial_scale_multiplier' in spec:
            raise ValueError('Default export scope cannot hide a scale change')
        return Decimal(1)
    if (scope != 'initial_view_scaled_native_share_form'
            or spec.get('family') != 'png_artifact'
            or type(spec.get('initial_scale_multiplier')) is not int
            or not 2 <= spec['initial_scale_multiplier'] <= 4
            or candidate.get('goal_revision', {}).get('derived_goal') != candidate.get('goal')
            or candidate.get('task_text_changed') is not True):
        raise ValueError('Explicit bounded initial-scale training derivative required')
    return Decimal(spec['initial_scale_multiplier'])


def target_scale(candidate, initial_value):
    """Use the independent initial native form, before any actor actions."""
    if not isinstance(initial_value, str):
        raise ValueError('Native initial scale text required')
    try:
        value = Decimal(initial_value)
    except InvalidOperation as exc:
        raise ValueError('Invalid native scale') from exc
    if not value.is_finite() or value <= 0:
        raise ValueError('Positive finite initial scale required')
    return format(value * multiplier(candidate), 'f')

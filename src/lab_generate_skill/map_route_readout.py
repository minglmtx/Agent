"""Typed native displayed route readouts, without equating a route with success.

The UI formatter is the installed OSM directions.js English protocol. Full
native route and geographic identity checks remain independent prerequisites.
Only the recorded visible summary is parsed; no answer goes to an actor input.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math
import re


def _nonnegative_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError('Native route numeric reference has an invalid type')
    try:
        value = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid native route numeric reference') from exc
    if not value.is_finite() or value < 0:
        raise ValueError('Native route numeric reference must be finite and nonnegative')
    return value


def native_distance(metres):
    metres = _nonnegative_number(metres)
    # The installed JS formats an IEEE-754 Number, including binary .toFixed
    # ties.  Decimal(str(1.15)) would incorrectly predict native 1.2, not 1.1.
    number = float(metres)
    if not math.isfinite(number):
        raise ValueError('Route distance is outside the native Number range')
    if metres < 1000:
        return {'value': str(Decimal.from_float(number).to_integral_value(rounding=ROUND_HALF_UP)), 'unit': 'm'}
    if metres < 10000:
        return {'value': str(Decimal.from_float(number / 1000).quantize(Decimal('.1'), rounding=ROUND_HALF_UP)), 'unit': 'km'}
    return {'value': str(Decimal.from_float(number / 1000).to_integral_value(rounding=ROUND_HALF_UP)), 'unit': 'km'}


def native_duration(seconds):
    seconds = _nonnegative_number(seconds)
    number = float(seconds)
    if not math.isfinite(number):
        raise ValueError('Route duration is outside the native Number range')
    total = int(Decimal.from_float(number / 60).to_integral_value(rounding=ROUND_HALF_UP))
    hours, minutes = divmod(total, 60)
    return {'hours': hours, 'minutes': minutes, 'display': f'{hours}:{minutes:02d}'}


def displayed_longest_turn_numbers(rows, independent_route):
    """Read the native turn-list distances, not hidden backend precision.

    Callers must bind these rows to the independently rendered full route and
    verify the actual route, endpoints and mode separately. The turn renderer
    has different rounding from the summary formatter above. In particular,
    two distinct backend distances can both display as 1200m.
    """
    legs = independent_route.get('legs') if isinstance(independent_route, dict) else None
    if not isinstance(legs, list) or len(legs) != 1 or not isinstance(legs[0], dict):
        raise ValueError('Complete single-leg native turn route required')
    steps = legs[0].get('steps')
    if (not isinstance(rows, list) or not rows or not isinstance(steps, list)
            or len(rows) != len(steps)):
        raise ValueError('Complete displayed turn rows and corresponding native steps required')
    distances = []
    for index, (row, step) in enumerate(zip(rows, steps), 1):
        if not isinstance(row, str) or not isinstance(step, dict):
            raise ValueError('Malformed native turn row or step')
        # innerText of tr.turn contains a final distance cell, including an
        # empty cell for arrival. Do not mistake numbers in a road name for it.
        match = re.fullmatch(r'\s*(\d+)\.\s+([^\t\r\n]+)\t([^\t\r\n]*)', row)
        if not match or int(match[1]) != index:
            raise ValueError('Native turn numbering or distance cell is incomplete')
        raw_distance = _nonnegative_number(step.get('distance'))
        cell = match[3].strip()
        if not cell:
            maneuver = step.get('maneuver')
            if (index != len(rows) or raw_distance != 0
                    or not isinstance(maneuver, dict) or maneuver.get('type') != 'arrive'):
                raise ValueError('Only the terminal zero-distance arrival may omit distance')
            continue
        value = re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)\s*(m|km)', cell)
        if not value:
            raise ValueError('Unsupported or incomplete displayed native distance')
        metres = Decimal(value[1]) * (1000 if value[2] == 'km' else 1)
        distances.append((index, metres))
    if not distances:
        raise ValueError('No displayed native distance segments available')
    largest = max(value for _, value in distances)
    return [index for index, value in distances if value == largest]


def visible_readout(state, independent_backend):
    if (not isinstance(state, dict) or state.get('loading') is not False
            or state.get('route_visible') is not True or not state.get('rows')
            or not isinstance(state.get('summary'), str)):
        raise ValueError('Native displayed route readout is unavailable')
    if not isinstance(independent_backend, dict):
        raise ValueError('Independent native backend route is unavailable')
    distance = native_distance(independent_backend['distance'])
    duration = native_duration(independent_backend['duration'])
    found = re.findall(r'\bDistance:\s*([0-9]+(?:\.[0-9]+)?)\s*(km|m)\.\s*Time:\s*([0-9]+):([0-5][0-9])\.',state['summary'])
    if len(found) != 1:
        raise ValueError('Native visible English route summary is missing or ambiguous')
    value, unit, hours, minutes = found[0]
    if (Decimal(value) != Decimal(distance['value']) or unit != distance['unit']
            or int(hours) != duration['hours'] or int(minutes) != duration['minutes']):
        raise ValueError('Visible native summary differs from its independent route reference')
    return {'distance': distance, 'duration': duration,
            'full_turn_rows': list(state['rows']),
            'native_distance_metres': str(_nonnegative_number(independent_backend['distance'])),
            'native_duration_seconds': str(_nonnegative_number(independent_backend['duration'])),
            'private_reference': True, 'geographic_identity_verified': False,
            'global_optimality_verified': False, 'normal_admission': False}


def distance_time_answer_checks(answer, readout, fields=('distance', 'duration')):
    """Strict explicit units; absent/wrong model output is ordinary false checks."""
    if not isinstance(answer, dict):
        return {k: False for k in fields}
    checks = {}
    for name in fields:
        actual = answer.get(name)
        expected = readout[name]
        if name == 'distance':
            valid = isinstance(actual, dict) and set(actual) == {'value', 'unit'} and actual.get('unit') in ('m', 'km')
            try:
                actual_metres = _nonnegative_number(actual.get('value') if isinstance(actual, dict) else None) * (1000 if isinstance(actual, dict) and actual.get('unit') == 'km' else 1)
                expected_metres = Decimal(expected['value']) * (1000 if expected['unit'] == 'km' else 1)
                valid = valid and actual_metres == expected_metres
            except ValueError:
                valid = False
        elif name == 'duration':
            valid = (isinstance(actual, dict) and set(actual) == {'hours', 'minutes'}
                and type(actual.get('hours')) is int and type(actual.get('minutes')) is int
                and actual['hours'] == expected['hours'] and actual['minutes'] == expected['minutes'])
        else:
            raise ValueError('Unsupported typed route answer field')
        checks[name] = bool(valid)
    return checks

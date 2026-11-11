"""Private native Export CPU controls from an independent observed DB expansion.

A smaller map rectangle may contain no objects. Private positive/negative
controls retain a real independently observed initial bbox node; they never
change task policy, an actor starting URL, or the strict nonempty XML reader.
"""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from . import map_osm_native_reference as expanded
from . import map_osm_artifact as artifact


def selection_change(database, *, precision, contain_center=None, exclude_center=None):
    """Propose one genuine native field change, never an actor instruction.

    Centers are (latitude, longitude) from a stable initial native public view.
    The rectangle stays inside the independently verified first selection.
    Every candidate must retain an actual initial bbox node with rounding margin.
    """
    if type(precision) is not int or not 0 <= precision <= 7:
        raise ValueError('Explicit actual native coordinate precision required')
    if contain_center is not None and exclude_center is not None:
        raise ValueError('A private control cannot both contain and exclude a center')
    reference = expanded.canonical_database(database, database.get('bounds'))
    original = list(map(Decimal, reference['bounds']))
    step = Decimal(1).scaleb(-precision)
    names = ('minlon', 'minlat', 'maxlon', 'maxlat')
    def center(value):
        if value is None: return None
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise ValueError('An actual public latitude/longitude center is required')
        lat, lon = (Decimal(artifact.coordinate(x)) for x in value)
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError('Public center outside geographical bounds')
        return lon, lat
    contained, excluded = center(contain_center), center(exclude_center)
    if contained is not None and not (original[0] <= contained[0] <= original[2] and original[1] <= contained[1] <= original[3]):
        raise ValueError('Verified first selection does not contain the original native center')
    candidates = []
    for ident in reference['initial_node_ids']:
        node = reference['objects']['node'][ident]
        anchor = Decimal(node['lon']), Decimal(node['lat'])
        for edge in range(4):
            axis = edge % 2; lower = edge < 2
            old = original[edge]
            if excluded is None:
                protected = [anchor[axis]] + ([contained[axis]] if contained is not None else [])
                end = min(protected) if lower else max(protected)
                target = (old + end) / 2
            else:
                if lower and anchor[axis] <= excluded[axis] + 4 * step: continue
                if not lower and anchor[axis] >= excluded[axis] - 4 * step: continue
                target = (anchor[axis] + excluded[axis]) / 2
            rounded = target.quantize(step, rounding=ROUND_FLOOR if lower else ROUND_CEILING)
            actual = list(original); actual[edge] = rounded
            if not actual[0] < actual[2] or not actual[1] < actual[3]: continue
            if abs(rounded - old) < 2 * step: continue
            if not (actual[0] + step < anchor[0] < actual[2] - step and actual[1] + step < anchor[1] < actual[3] - step): continue
            if any(actual[i] < original[i] for i in (0, 1)) or any(actual[i] > original[i] for i in (2, 3)): continue
            if contained is not None and not (actual[0] + step < contained[0] < actual[2] - step and actual[1] + step < contained[1] < actual[3] - step): continue
            if excluded is not None and actual[0] <= excluded[0] <= actual[2] and actual[1] <= excluded[1] <= actual[3]: continue
            score = abs(rounded - old) / (original[axis + 2] - original[axis])
            candidates.append((score, ident, edge, actual))
    if not candidates:
        raise ValueError('No independently supported distinct nonempty native rectangle available')
    _, ident, edge, values = max(candidates, key=lambda x: (x[0], x[1], -x[2]))
    return {'field': names[edge], 'value': str(values[edge]), 'expected_bounds': list(artifact.bbox(values)),
            'independent_initial_node_id': ident, 'reference_bounds': reference['bounds'],
            'actual_initial_node_retained': True, 'actual_public_center_contained': contained is not None,
            'actual_public_center_excluded': excluded is not None, 'original_actor_start_changed': False,
            'actor_strategy_modified': False, 'force_click': False, 'fake_change_event': False}

"""Full native request precision scoped to local layer bbox transport only.

The existing direct-export artifact API stays byte-for-byte unchanged. Native
XML remains seven decimals and stored node precision remains unchanged.
"""
from decimal import Decimal,InvalidOperation
from .map_osm_artifact import *


def bounds_coordinate(value):
    """Keep exact finite native request bounds, separate from stored nodes.

    Leaflet submits full floating-point decimal bounds. Seven decimal places
    is the OSM node-storage precision, not a constraint on the request window.
    No request coordinate is quantized or converted through a binary float.
    """
    if isinstance(value,bool)or not isinstance(value,(str,int,float,Decimal)):
        raise ValueError('Malformed native request bound')
    text=str(value)
    if len(text)>256:raise ValueError('Native bound exceeds numeric inspection budget')
    try:result=Decimal(text)
    except (InvalidOperation,TypeError,ValueError):raise ValueError('Malformed native request bound')from None
    if not result.is_finite():raise ValueError('Non-finite native request bound')
    if not -180<=result<=180:raise ValueError('Native bound outside geographic range')
    if abs(result.as_tuple().exponent)>256:raise ValueError('Native bound exceeds numeric inspection budget')
    # Decimal.normalize() is context-sensitive and can round long input. Fixed
    # formatting followed by insignificant zero removal retains the exact value.
    formatted=format(result,'f')
    if '.'in formatted:formatted=formatted.rstrip('0').rstrip('.')
    return formatted if result else '0'


def bbox(values):
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError('Four native export bounds required')
    result = tuple(bounds_coordinate(v) for v in values)
    west, south, east, north = map(Decimal, result)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError('Invalid native export rectangle')
    return result


def native_xml_bbox(values):
    """Native BoundingBox.add_bounds_to serializes bounds with %.7f.

    This describes XML serialization only. It never replaces the full request
    bounds used to select the independent native database reference.
    """
    return bbox([format(float(Decimal(v)),'.7f')for v in bbox(values)])


def bbox_area(values):
    west,south,east,north=map(Decimal,bbox(values))
    return (east-west)*(north-south)

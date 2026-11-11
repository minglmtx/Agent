"""Place identities from the pinned geocoder, never from query-name similarity.

These building blocks do not admit tasks on their own. Live page controls,
reset evidence and the native object-page capability are required by callers.
"""
import math
import re
from urllib.parse import urlsplit,parse_qs


def identity(record):
    kind=record.get('osm_type');number=record.get('osm_id')
    if kind not in ('node','way','relation') or isinstance(number,bool):
        raise ValueError('Invalid native place identity')
    if not re.fullmatch(r'[1-9][0-9]*',str(number)):
        raise ValueError('Invalid native place ID')
    return kind,int(number)


def bounds(record):
    south,north,west,east=map(float,record['boundingbox'])
    lat,lon=float(record['lat']),float(record['lon'])
    if not (all(math.isfinite(x)for x in (south,north,west,east,lat,lon))
            and -90<=south<=lat<=north<=90 and -180<=west<=lon<=east<=180):
        raise ValueError('Invalid native geographic extent')
    return south,north,west,east


def select_reference(records,kind,number):
    """Caller must establish the requested identity from source evidence."""
    matches=[r for r in records if identity(r)==(kind,number)]
    if len(matches)!=1:raise ValueError('Requested geographic object is missing or ambiguous')
    bounds(matches[0])
    return matches[0]


def public_result_matches(reference,public):
    """Require the actual result link's OSM identity and native coordinates."""
    kind,number=identity(reference);south,north,west,east=bounds(reference)
    if not isinstance(public,dict):return False
    attrs=public.get('attributes',{})
    try:
        path=urlsplit(public['path'])
        if path.scheme or path.netloc or path.path!=f'/{kind}/{number}':return False
        if attrs.get('data-type')!=kind or attrs.get('data-id')!=str(number):return False
        expected={'data-lat':float(reference['lat']),'data-lon':float(reference['lon']),
                  'data-min-lat':south,'data-max-lat':north,'data-min-lon':west,'data-max-lon':east}
        return all(math.isfinite(float(attrs[k])) and abs(float(attrs[k])-v)<=1e-7 for k,v in expected.items())
    except (ValueError,TypeError,KeyError):return False


def native_view_in_place(reference,view):
    """Cross-check two map-derived signals, independent of an editable URL."""
    from .map_view import native_zoom
    south,north,west,east=bounds(reference)
    try:
        native_zoom(view)
        geo=re.fullmatch(r'geo:([-+]?\d+(?:\.\d+)?),([-+]?\d+(?:\.\d+)?)\?z=(\d+)',view['native_geo_uri'])
        lat,lon=map(float,geo.groups()[:2])
        values=parse_qs(urlsplit(view['native_long_link']).fragment)['map'][0].split('/')
        link_lat,link_lon=map(float,values[1:])
        # Long links are rounded by Leaflet's zoom precision. A malicious or
        # stale geographic signal must not redirect identity to another place.
        precision=[len(s.partition('.')[2]) for s in values[1:]]
        agreement=all(abs(a-b)<=.5*10**(-digits)+1e-8 for a,b,digits in zip((lat,lon),(link_lat,link_lon),precision))
        return (view['map_visible'] and agreement and bool(view.get('tiles')) and
                south-1e-6<=lat<=north+1e-6 and west-1e-6<=lon<=east+1e-6)
    except (ValueError,TypeError,KeyError,AttributeError):return False

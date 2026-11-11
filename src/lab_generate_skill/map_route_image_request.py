"""Bind a public raster request to an independently captured complete route.

The bounds and scale may vary: only the explicitly requested full driving route
and its inclusion in the image are fixed. Artifact/provenance/pixel validation
remain separate; a matching request alone never establishes task success.
"""
from .map_raster_request import normalize, MAX_POINTS
from .map_route_normal_capture import complete_route, fingerprint, exact_pair


def decode_polyline(encoded):
    if not isinstance(encoded,str) or not encoded or len(encoded)>MAX_POINTS*16:
        raise ValueError('Bounded native step geometry required')
    offset=0;totals=[0,0];points=[]
    while offset<len(encoded):
        for axis in (0,1):
            value=shift=0
            while True:
                if offset>=len(encoded) or shift>30:raise ValueError('Truncated native geometry')
                chunk=ord(encoded[offset])-63;offset+=1
                if not 0<=chunk<=63:raise ValueError('Malformed native geometry')
                value|=(chunk&31)<<shift;shift+=5
                if chunk<32:break
            totals[axis]+=~(value>>1) if value&1 else value>>1
        point=[n/100000 for n in totals]
        if not(-90<=point[0]<=90 and -180<=point[1]<=180):raise ValueError('Native geometry outside globe')
        points.append(point)
        if len(points)>MAX_POINTS:raise ValueError('Native geometry exceeds bounded renderer')
    return points


def native_line(reference):
    if (reference.get('profile')!='car' or reference.get('independent_native_read') is not True
            or reference.get('body_sha256')!=fingerprint(reference['body'])
            or not exact_pair(reference.get('pair'),reference.get('pair'))):
        raise ValueError('Independent driving-route reference is unbound')
    route=complete_route(reference['body']);line=[]
    # Native FOSSGISOSRMEngine._transformSteps concatenates all decoded step
    # geometries at precision 5, including the duplicated boundary points.
    for step in route['legs'][0]['steps']:line.extend(decode_polyline(step['geometry']))
    if not 2<=len(line)<=MAX_POINTS:raise ValueError('Full native route exceeds renderer support')
    return line


def check_request(request,references):
    if not isinstance(references,list) or not references:raise ValueError('Independent route alternatives required')
    lines=[native_line(ref)for ref in references]
    # Receipt uses normalized public fields, not arbitrary actor metadata.
    public={k:request[k]for k in ('bbox','scale','format','route')}
    actual=normalize(public)
    if actual!=request:raise ValueError('Owned renderer request is inconsistent')
    route=actual['route']
    match=any(len(line)==len(route) and all(abs(a-b)<=1e-9 for p,q in zip(line,route)for a,b in zip(p,q)) for line in lines)
    w,s,e,n=actual['bbox']
    inside=bool(route) and all(s<=lat<=n and w<=lon<=e for lat,lon in route)
    return dict(complete_requested_driving_geometry=match,whole_route_inside_export=inside,
                png_format=actual['format']=='png')

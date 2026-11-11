"""Bounded public raster requests; no target task or private answer is accepted."""
import math

RADIUS=6378137.0
MAX_PIXELS=4_000_000
MAX_POINTS=20000


def export_byte_limit(file_format):
    # Vector PDFs can be much larger than PNGs at identical page dimensions.
    # A native 1385x894 map produced 79 MB; preserve its geography and vectors.
    if file_format == 'pdf':return 128*1024*1024
    if file_format == 'png':return 16*1024*1024
    raise ValueError('Unsupported native export format')


def number(value):
    if isinstance(value,bool) or not isinstance(value,(str,int,float)):
        raise ValueError('Finite numeric value required')
    n=float(value)
    if not math.isfinite(n):raise ValueError('Finite numeric value required')
    return n


def project(lon,lat):
    return (RADIUS*math.radians(lon),RADIUS*math.log(math.tan(math.pi/4+math.radians(lat)/2)))


def normalize(payload, *, allow_pdf=False):
    if not isinstance(payload,dict)or set(payload)!={'bbox','scale','format','route'}:
        raise ValueError('Only declared public raster fields accepted')
    if payload['format'] not in (('png','pdf') if allow_pdf else ('png',)):
        raise ValueError('Format is not enabled in this local export profile')
    bounds=payload['bbox']
    if not isinstance(bounds,list)or len(bounds)!=4:raise ValueError('Four bounds required')
    w,s,e,n=map(number,bounds)
    if not(-180<=w<e<=180 and -85.05112878<s<n<85.05112878):raise ValueError('Valid Web Mercator bounds required')
    scale=number(payload['scale'])
    if scale<=0:raise ValueError('Positive scale required')
    x0,y0=project(w,s);x1,y1=project(e,n)
    width=max(1,math.floor((x1-x0)/scale/.00028+.5));height=max(1,math.floor((y1-y0)/scale/.00028+.5))
    if width>4096 or height>4096 or width*height>MAX_PIXELS:raise ValueError('Native raster dimensions exceed bounded render budget')
    route=payload['route']
    if not isinstance(route,list)or len(route)>MAX_POINTS or len(route)==1:raise ValueError('Bounded route polyline required')
    line=[]
    for point in route:
        if not isinstance(point,list)or len(point)!=2:raise ValueError('Native latitude/longitude pair required')
        lat,lon=map(number,point)
        if not(-85.05112878<lat<85.05112878 and -180<=lon<=180):raise ValueError('Route coordinate outside projection')
        line.append([lat,lon])
    return dict(bbox=[w,s,e,n],scale=scale,format=payload['format'],route=line,width=width,height=height,
                projected_bounds=[x0,y0,x1,y1])

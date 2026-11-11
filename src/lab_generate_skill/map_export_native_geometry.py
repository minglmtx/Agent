"""Native Export panel/geometry readers and private pointer controls.

Standalone replacement draft for the erroneous historical marker selector and
continuous-origin projection. No actor policy, task admission, or downloads.
"""
from decimal import Decimal
import math
import time

from . import map_frontier_capabilities as cap
from . import map_panel as legacy_panel

VERSION = 'native-export-pixel-origin-and-location-filter-v1'
RESIZE_SELECTOR = '#map .location-filter.resize-marker'
MOVE_SELECTOR = '#map .location-filter.move-marker'

# The native plugin uses four resize markers plus one move marker. An arbitrary
# marker or the nonexistent .leaflet-locationfilter-handle is not evidence.
_OLD = "visible(document.querySelector('.leaflet-locationfilter-handle'))"
_NEW = "([...document.querySelectorAll('#map .location-filter.resize-marker')].filter(visible).length===4&&[...document.querySelectorAll('#map .location-filter.move-marker')].filter(visible).length===1)"
if legacy_panel.READ.count(_OLD) != 1:
    raise RuntimeError('Native export panel compatibility changed; review required')
READ_PANEL = legacy_panel.READ.replace(_OLD, _NEW)
READ_SELECTION = r'''() => {
 const map=document.querySelector('#map');
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
 if(!visible(map))return {map_visible:false,markers:[]};
 const m=map.getBoundingClientRect();
 const markers=[...map.querySelectorAll('.location-filter.resize-marker,.location-filter.move-marker')].map(e=>{
   const r=e.getBoundingClientRect(),resize=e.classList.contains('resize-marker');
   // Actual plugin DivIcon anchors: resize [7,6], move [-10,-10].
   return {kind:resize?'resize':'move',visible:visible(e),width:r.width,height:r.height,
      x:r.left-m.left+(resize?7:-10),y:r.top-m.top+(resize?6:-10)};
 });
 return {map_visible:true,width:map.clientWidth,height:map.clientHeight,map_left:m.left,map_top:m.top,markers};
}'''


def read_map_panel(page):
    if page.locator('form.export_form:visible').count():
        page.wait_for_function("() => ['minlon','minlat','maxlon','maxlat'].every(n=>{const e=document.querySelector('form.export_form [name=\"'+n+'\"]');return e&&e.value.trim()!==''&&Number.isFinite(Number(e.value))})",timeout=10000)
    return page.evaluate(READ_PANEL)


def selection_state(page):
    return page.evaluate(READ_SELECTION)


def _size(size):
    if not isinstance(size,dict) or set(size)!={'width','height'}:
        raise ValueError('Native map size requires exactly width and height')
    if any(type(size[k]) is not int or not 256<=size[k]<=4096 for k in size):
        raise ValueError('Native map size out of supported range')
    return size['width'],size['height']


def _project(lat,lon,world):
    latitude=max(-85.0511287798,min(85.0511287798,lat))
    sine=math.sin(math.radians(latitude))
    return ((lon+180)/360*world,
        (.5-math.log((1+sine)/(1-sine))/(4*math.pi))*world)


def _unproject_y(y,world):
    return math.degrees(math.atan(math.sinh(math.pi*(1-2*y/world))))


def _round(value):
    # JS Math.round, including negative values (Python round uses ties-to-even).
    return math.floor(value+.5)


def _precision(zoom):
    return max(0,math.ceil(math.log2(max(1,zoom))))


def _origins(view,size):
    zoom,lat,lon=cap.native_view(view);width,height=_size(size)
    world=256*2**zoom
    x,y=_project(lat,lon,world)
    primary=(_round(x-width/2),_round(y-height/2))
    # Public native geolink is formatted by OSM.zoomPrecision. Its last digit
    # may hide a boundary crossing. Enumerate the *bounded native pixel origins*
    # compatible with that formatting instead of adding an arbitrary degree tol.
    half=10**-_precision(zoom)/2
    xl,_=_project(lat,lon-half,world);xh,_=_project(lat,lon+half,world)
    _,yl=_project(lat+half,lon,world);_,yh=_project(lat-half,lon,world)
    xs=range(_round(xl-width/2),_round(xh-width/2)+1)
    ys=range(_round(yl-height/2),_round(yh-height/2)+1)
    if len(xs)>256 or len(ys)>256:
        raise ValueError('Public native center precision insufficient for geometry')
    return zoom,world,width,height,primary,tuple((a,b)for a in xs for b in ys)


def _at(origin,world,width,height):
    x,y=origin
    return (x/world*360-180,_unproject_y(y+height,world),
        (x+width)/world*360-180,_unproject_y(y,world))


def projected_bounds(view,size):
    _,world,w,h,origin,_=_origins(view,size)
    return tuple(str(x)for x in _at(origin,world,w,h))


def bounds_match_projection(values,view,size):
    actual=cap.bounds(values)
    zoom,world,w,h,_,origins=_origins(view,size)
    tolerance=Decimal(1).scaleb(-_precision(zoom))/2+Decimal('0.000000001')
    return any(all(abs(Decimal(a)-Decimal(str(b)))<=tolerance
        for a,b in zip(actual,_at(origin,world,w,h)))for origin in origins)


def active_selection(state):
    if state.get('map_visible')is not True:return False
    markers=state.get('markers')
    if not isinstance(markers,list):return False
    resize=[m for m in markers if m.get('kind')=='resize']
    move=[m for m in markers if m.get('kind')=='move']
    if len(resize)!=4 or len(move)!=1:return False
    return all(m.get('visible')is True and all(type(m.get(k))in(int,float)and math.isfinite(m[k])
        for k in ('width','height','x','y'))and m['width']>0 and m['height']>0 for m in markers)


def selection_bounds_match(values,view,state):
    """Compare actual form to public visible native corner geometry.

    Marker positions are rounded by Leaflet. Bound each coordinate by half a
    world pixel plus native text precision, retaining real wrong-area rejection.
    """
    if not active_selection(state):return False
    markers=[m for m in state['markers']if m['kind']=='resize']
    west=min(m['x']for m in markers);east=max(m['x']for m in markers)
    north=min(m['y']for m in markers);south=max(m['y']for m in markers)
    if not west<east or not north<south:return False
    # Four corners must describe one rectangle, not unrelated map markers.
    corners={(round(m['x'],3),round(m['y'],3))for m in markers}
    if len(corners)!=4 or any(min(abs(m['x']-west),abs(m['x']-east))>.01 or
        min(abs(m['y']-north),abs(m['y']-south))>.01 for m in markers):return False
    actual=tuple(Decimal(v)for v in cap.bounds(values))
    zoom,world,_,_,_,origins=_origins(view,{'width':state['width'],'height':state['height']})
    half=Decimal(1).scaleb(-_precision(zoom))/2+Decimal('0.000000001')
    for ox,oy in origins:
        intervals=[((ox+west-.5)/world*360-180,(ox+west+.5)/world*360-180),
            (_unproject_y(oy+south+.5,world),_unproject_y(oy+south-.5,world)),
            ((ox+east-.5)/world*360-180,(ox+east+.5)/world*360-180),
            (_unproject_y(oy+north+.5,world),_unproject_y(oy+north-.5,world))]
        if all(Decimal(str(low))-half<=value<=Decimal(str(high))+half
            for value,(low,high)in zip(actual,intervals)):return True
    return False


def wait_selection(page,*,timeout=10000):
    deadline=time.monotonic()+timeout/1000;last=None;signature=None;stable_at=None
    while time.monotonic()<deadline:
        last=selection_state(page)
        current=repr(last.get('markers')) if active_selection(last) else None
        if current is not None and current==signature:
            if time.monotonic()-stable_at>=.2:return last
        else:signature=current;stable_at=time.monotonic()
        page.wait_for_timeout(50)
    raise TimeoutError('Native LocationFilter four resize + one move markers not stable')


def drag_northwest_corner(page,*,delta=(20,20),timeout=10000):
    """Private capability positive: actual native pointer drag, never actor hint."""
    before=wait_selection(page,timeout=timeout)
    if len(delta)!=2 or any(type(v)not in(int,float)or not math.isfinite(v)for v in delta):
        raise ValueError('Finite private pointer delta required')
    corner=min((m for m in before['markers']if m['kind']=='resize'),key=lambda m:(m['y'],m['x']))
    x,y=corner['x'],corner['y'];tx,ty=x+delta[0],y+delta[1]
    if not 1<tx<before['width']-1 or not 1<ty<before['height']-1:
        raise ValueError('Private native pointer target must remain inside map')
    page.mouse.move(before['map_left']+x,before['map_top']+y)
    page.mouse.down()
    try:page.mouse.move(before['map_left']+tx,before['map_top']+ty,steps=8)
    finally:page.mouse.up()
    after=wait_selection(page,timeout=timeout)
    return {'before':before,'after':after,'actual_pointer_drag':True,
        'force_click':False,'fake_change_event':False,'actor_hint':False}


def wait_export(page,*,timeout=15000):
    """Stable initialized native form, using the corrected public panel reader."""
    deadline=time.monotonic()+timeout/1000;previous=None;stable=None
    while time.monotonic()<deadline:
        # One absolute budget; do not nest the compatibility reader's 10s wait.
        panel=page.evaluate(READ_PANEL)
        try:values=cap.form_bounds(panel)
        except (KeyError,TypeError,ValueError):values=None
        current=(values,panel.get('export_form',{}).get('submit_visible'))
        if values is not None and current==previous:
            if time.monotonic()-stable>=.25:return panel,values
        else:previous=current;stable=time.monotonic()
        page.wait_for_timeout(50)
    raise TimeoutError('Native initialized export form did not stabilize')

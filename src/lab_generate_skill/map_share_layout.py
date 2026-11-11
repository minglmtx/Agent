"""Independent Leaflet pixel-origin calculation for native Share sidebar resize."""
import math


def validated_layouts(proof):
    """Require the same independently validated paths/layouts on both resets."""
    if (proof.get('passed') is not True or proof.get('independent_baselines_equal') is not True
            or len(proof.get('cycles',[]))!=2):
        raise ValueError('Two independent native Share layout cycles required')
    layouts=[];baselines=[]
    for cycle in proof['cycles']:
        if cycle.get('passed') is not True or cycle.get('protected_state_unchanged') is not True:
            raise ValueError('Share layout cycle did not preserve its baseline')
        rows={}
        for row in cycle.get('records',[]):
            if row.get('passed') is not True or not row.get('checks') or not all(row['checks'].values()):
                raise ValueError('Native Share layout failed')
            if row['path'] in rows:raise ValueError('Repeated layout path')
            # Verify the shape independently from a top-level pass flag.
            resized_center(7,42.896,-75.108,row['geometry'])
            rows[row['path']]=row['geometry']
        if not rows or not cycle.get('initial_fingerprint'):
            raise ValueError('Missing layout records or baseline')
        layouts.append(rows);baselines.append(cycle['initial_fingerprint'])
    if layouts[0]!=layouts[1] or baselines[0]!=baselines[1]:
        raise ValueError('Share layout reset differs')
    return layouts[0]


def resized_center(zoom,latitude,longitude,geometry):
    if (type(zoom)is not int or not 1<=zoom<=20 or
            not all(math.isfinite(v)for v in (latitude,longitude)) or abs(latitude)>85 or abs(longitude)>180):
        raise ValueError('Invalid original map center')
    if set(geometry)!={'before','after'}:raise ValueError('Native before/after map size required')
    for size in geometry.values():
        if set(size)!={'width','height'} or any(type(v)is not int or v<256 for v in size.values()):
            raise ValueError('Invalid native map dimensions')
    before,after=geometry['before'],geometry['after']
    if before['width']-after['width']!=250 or before['height']!=after['height']:
        raise ValueError('Unverified native Share sidebar layout')
    world=256*2**zoom;sin=math.sin(math.radians(latitude))
    x=(longitude+180)/360*world
    y=(.5-math.log((1+sin)/(1-sin))/(4*math.pi))*world
    # Leaflet _getNewPixelOrigin().round(), then getCenter() after
    # invalidateSize({pan:false}). No task target is read from the final page.
    px=math.floor(x-before['width']/2+.5)+after['width']/2
    py=math.floor(y-before['height']/2+.5)+after['height']/2
    return zoom, math.degrees(math.atan(math.sinh(math.pi-2*math.pi*py/world))), px/world*360-180


def map_size(page):
    return page.locator('#map').evaluate('e=>({width:e.clientWidth,height:e.clientHeight})')


def open_native_share(page):
    # CPU reference capture only. Existing visibility must not toggle closed.
    if not page.locator('.share-ui').is_visible():
        page.locator('.control-share .control-button').click()
    page.locator('.share-ui:visible').wait_for(timeout=10000)


def open_verified_share(page, geometry):
    """CPU reference capture must use the admitted viewport/sidebar geometry."""
    before=map_size(page)
    open_native_share(page)
    if {'before':before,'after':map_size(page)}!=geometry:
        raise ValueError('Live native Share layout differs from validated reference geometry')

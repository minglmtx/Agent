"""Final-only GPS overlay checks over native state and genuine frozen tiles.

No browser actions, network requests, guessed GPX tracks or actor guidance.
A checkbox alone is insufficient; visible pixels and complete loading matter.
"""
import hashlib
from io import BytesIO
import math
from urllib.parse import urlsplit
from PIL import Image
from .map_frozen_provider_runtime import same_view, covered_area
from .map_provider_contract import validate_resource_family

VERSION = 'native-gps-overlay-terminal-v1'


def tile_checks(initial, terminal, server, response_hashes):
    checks = dict(same_initial_area=False,native_gps_overlay=False,
        loaded_genuine_tiles=False,complete_visible_coverage=False,visible_recorded_traces=False)
    try:
        checks['same_initial_area'] = same_view(initial,terminal)
        checks['native_gps_overlay'] = (terminal['enabled'] is True and terminal['code']=='G'
            and terminal['template']==server.url+'/tiles/gps/{z}/{x}/{y}.png')
        width,height=terminal['size']['x'],terminal['size']['y']
        if not all(type(v)in(int,float) and math.isfinite(v) and v>0 for v in (width,height)):
            return checks
        rectangles=[];valid=True;count=0;visible=False
        for t in terminal['tiles']:
            left,top,right,bottom=t['rect']
            if not all(type(v)in(int,float)and math.isfinite(v)for v in t['rect']):return checks
            if not t['current'] or right<=0 or bottom<=0 or left>=width or top>=height:continue
            count+=1
            if right<=left or bottom<=top:return checks
            z,x,y=(t['coords'][k]for k in ('z','x','y'))
            if not(all(type(v)is int for v in (z,x,y))and 0<=z<=20 and 0<=x<2**z and 0<=y<2**z):return checks
            path=f'/tiles/gps/{z}/{x}/{y}.png';data=server.bodies.get(path)
            okay=(t['loaded']is True and t['src']==server.url+path and data is not None
                  and response_hashes.get(t['src'])==hashlib.sha256(data).hexdigest())
            valid=valid and okay
            if not okay:continue
            with Image.open(BytesIO(data))as image:
                if image.format!='PNG' or image.size!=(256,256):return checks
                # Use the actual unclipped browser rectangle to exclude trace
                # pixels lying outside the viewport, including sidebar resize.
                box=(math.floor(max(0,-left)/(right-left)*256),
                     math.floor(max(0,-top)/(bottom-top)*256),
                     math.ceil(min(right-left,width-left)/(right-left)*256),
                     math.ceil(min(bottom-top,height-top)/(bottom-top)*256))
                visible |= image.convert('RGBA').getchannel('A').crop(box).getbbox() is not None
            rectangles.append(t['rect'])
        checks['loaded_genuine_tiles']=count>0 and valid
        checks['complete_visible_coverage']=covered_area(rectangles,width,height)>=width*height-1
        checks['visible_recorded_traces']=visible
    except (KeyError,TypeError,ValueError,OverflowError,OSError):pass
    return checks


def evaluate(spec,*,initial,terminal,page,site_origin,server,response_hashes,
             integrity=True,runtime_error=None,capture_error=None):
    validate_resource_family(spec)
    if spec.get('family')!='gps_overlay':raise ValueError('GPS overlay task required')
    checks={}
    def result(status,reason):
        return dict(version=VERSION,status=status,reward={'success':1.,'failure':0.,'unknown':None}[status],checks=checks,reason=reason)
    if runtime_error or capture_error or integrity is not True:
        return result('unknown','Runtime or complete native capture unavailable.')
    if (not isinstance(page,dict) or type(page.get('http_status'))is not int
            or not isinstance(page.get('url'),str)
            or any(type(page.get(k))is not bool for k in ('login_page','error_page'))):
        return result('unknown','Final document capture is incomplete.')
    status=page['http_status']
    if status<200 or status>=500:return result('unknown','Final document transport failed.')
    actual,expected=urlsplit(page['url']),urlsplit(site_origin)
    checks['valid_final_map_document']=(200<=status<300 and not page['login_page']and not page['error_page']
        and (actual.scheme,actual.netloc)==(expected.scheme,expected.netloc))
    if not checks['valid_final_map_document']:return result('failure','Final page is not a valid map document.')
    if not isinstance(initial,dict)or initial.get('enabled')is not False:
        return result('unknown','A declared initial view with GPS disabled is required.')
    if isinstance(terminal,dict) and terminal.get('map_visible') is False:
        checks['native_map_visible']=False
        return result('failure','No visible map is present in the final document.')
    if not isinstance(terminal,dict):
        return result('unknown','Native terminal overlay capture is unavailable.')
    if type(terminal.get('enabled'))is not bool:return result('unknown','Native overlay state missing.')
    checks['gps_enabled']=terminal['enabled']
    if not checks['gps_enabled']:return result('failure','Requested overlay is not enabled at termination.')
    try:
        same_view(initial,terminal)
    except (KeyError,TypeError,ValueError,OverflowError):
        return result('unknown','Native map view capture is incomplete.')
    checks.update(tile_checks(initial,terminal,server,response_hashes))
    if not checks['same_initial_area']:return result('failure','Final map area differs from the public task.')
    if not all(checks.values()):
        return result('unknown','Overlay selection lacks complete genuine visible GPS image evidence.')
    return result('success','Genuine public GPS tracks are visible over the declared initial map area.')

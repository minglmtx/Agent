"""Native short-map links with original-view references independent of ports.

The encoder follows the pinned leaflet.map.js; CPU controls independently read
the website output. Route delivery and external messaging are not implied.
"""
import math
from urllib.parse import urlsplit,parse_qs
from .map_metadata_query import initial_view,verify_sources
from .site_query_rules import reference_fingerprint
from .map_share_layout import resized_center,open_verified_share


def short_path(zoom,lat,lon):
    if type(zoom)is not int or not 1<=zoom<=20 or not all(math.isfinite(x)for x in (lat,lon)) or abs(lat)>85 or not -180<=lon<180:
        raise ValueError('Unsupported short-link map view')
    x=math.floor((lon+180)*(2**30/90)+.5)
    y=math.floor((lat+90)*(2**30/45)+.5)
    def interlace(x,y):
        value=0
        for bit in range(15):
            value|=((x>>bit)&1)<<(2*bit+1)
            value|=((y>>bit)&1)<<(2*bit)
        return value
    first=interlace(x>>17,y>>17);second=interlace((x>>2)&0x7fff,(y>>2)&0x7fff)
    alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_~'
    chars=[]
    for i in range(math.ceil((zoom+8)/3)):
        word=first if i<5 else second
        chars.append(alphabet[(word>>(24-6*(i if i<5 else i-5)))&63])
    return '/go/'+''.join(chars)+'-'*((zoom+8)%3)


def validate(q):
    if q.get('family')!='map_share' or q.get('kind')!='short_link' or q.get('fields')!={'short_link':'local_url'}:
        raise ValueError('Unsupported map share schema')
    path=urlsplit(q['reference_path'])
    if path.path!='/' or path.query or set(parse_qs(path.fragment))!={'map'}:
        raise ValueError('An unmarked original standard map view is required')
    short_path(*initial_view(q['reference_path']))
    resized_center(*initial_view(q['reference_path']),q['share_geometry'])
    required={'app/assets/javascripts/leaflet.map.js','app/assets/javascripts/leaflet.share.js',
              'app/assets/javascripts/leaflet.sidebar.js','app/assets/stylesheets/common.scss'}
    if not required<={r['path']for r in q.get('source_evidence',[])if not r.get('installed')}:
        raise ValueError('Pinned native link implementation required')


def reference(site,q):
    validate(q);verify_sources(site,q)
    return {'object_id':'map-share:'+reference_fingerprint({'path':q['reference_path'],'kind':q['kind']}),
            'values':{'short_link':short_path(*resized_center(*initial_view(q['reference_path']),q['share_geometry']))},
            'reference_source':'pinned native encoder and original map view; live origin checked separately'}


def ui_values(page,q,*,evidence=None):
    from .map_view import wait_native_view
    from .local_url_query import same_local_url
    validate(q);u=urlsplit(page.url);origin=u.scheme+'://'+u.netloc
    page.goto('about:blank')
    page.goto(origin+q['reference_path'],wait_until='domcontentloaded',timeout=60000)
    view=wait_native_view(page,q['reference_path'])
    open_verified_share(page,q['share_geometry'])
    page.locator('.share-ui #short_link').click()
    field=page.locator('.share-ui #short_input:visible');field.wait_for(state='visible',timeout=10000)
    value=field.input_value();link=page.locator('.share-ui #short_link').get_attribute('href')
    if value!=link or not same_local_url(value,urlsplit(value).path,origin):
        raise ValueError('Native short link is unavailable or points outside this deployment')
    if evidence is not None:evidence.append({'url':page.url,'native_view':view,'native_short_link':value})
    return {'short_link':value}

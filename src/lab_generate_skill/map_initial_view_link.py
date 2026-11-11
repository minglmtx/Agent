"""Result-only local map-link contract, bound to the real initial native view.

Candidate replacement for Share-panel process requirements. The returned link
must identify the original center, zoom and Standard layer. Opening a sidebar
is neither necessary nor sufficient; external delivery is outside this scope.
"""
from urllib.parse import urlsplit,parse_qs
from .admin_query_rules import parse_answer
from .map_local_capabilities import geo_triplet,map_triplet,same_center
from .map_metadata_query import initial_view
from .map_share_query import short_path
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint
VERSION='map-initial-view-link-result-v1'


def local_link(value,origin,center):
    if not isinstance(value,str):return False
    try:
        p=urlsplit(value);base=urlsplit(origin)
        if p.scheme not in ('http','https')or(p.scheme,p.netloc)!=(base.scheme,base.netloc)or p.username is not None or p.password is not None:return False
        if p.path.startswith('/go/'):
            return not p.query and not p.fragment and p.path==short_path(*center)
        if p.path!='/'or p.query:return False
        fields=parse_qs(p.fragment,keep_blank_values=True)
        if set(fields)-{'map','layers'}or any(len(v)!=1 for v in fields.values())or fields.get('layers',['M'])not in (['M'],['']):return False
        return same_center(center,map_triplet(value))
    except(ValueError,TypeError,KeyError,OverflowError):return False


def reference(contract,view,site_origin):
    expected=initial_view(contract['start_path']);path=urlsplit(contract['start_path'])
    if path.path!='/'or path.query or set(parse_qs(path.fragment))!={'map'}:raise ValueError('Explicit original unmarked map view required')
    center=geo_triplet(view)
    if view.get('map_visible')is not True or not same_center(expected,center):raise ValueError('Actual initial native map differs from original task view')
    # Native map links are emitted from the map object; editable Share inputs
    # alone are not proof of the original coordinates.
    if not local_link(view.get('native_long_link'),site_origin,center):raise ValueError('Native initial map link disagrees with native geo URI')
    content={'version':VERSION,'source_task_id':contract['source_task_id'],'start_path':contract['start_path'],
             'center':list(center),'layer':'M','goal':contract['goal']}
    return content|{'sha256':reference_fingerprint(content)}


def evaluate(contract,page,answer,initial,final,*,site_origin,runtime_error=None):
    def unknown(why):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':why}
    if runtime_error:return unknown('Runtime error prevents reliable result verification')
    if initial!=final or not isinstance(initial,dict):return unknown('Original native reference missing or changed')
    content={k:v for k,v in initial.items()if k!='sha256'}
    if (initial.get('sha256')!=reference_fingerprint(content)or initial.get('version')!=VERSION or
        any(initial.get(k)!=contract.get(k)for k in ('source_task_id','start_path','goal'))):return unknown('Initial reference identity mismatch')
    if not isinstance(page,dict)or type(page.get('http_status'))is not int:return unknown('Terminal document health missing')
    if page['http_status']>=500:return unknown('Terminal server error')
    try:value=parse_answer(answer);schema=set(value)=={'share_link'}and isinstance(value['share_link'],str)
    except(ValueError,TypeError):value={};schema=False
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),'answer_schema':schema,
            'initial_view_and_layer_link':schema and local_link(value.get('share_link'),site_origin,initial['center'])}
    passed=all(checks.values())
    return {'version':VERSION,'status':'success'if passed else'failure','reward':float(passed),'checks':checks,'reason':None}

"""Optional native MapData XHR compatibility, never a native single-map export.

All requests retain the installed API's50K limit. Only an observed, recognized
node-cap400 permits subdivision. Decimal rectangles exactly cover the original
request. Actual200 XML children are deduplicated without losing outside-bbox
way nodes or parent relations. The merged envelope is explicitly adapted data;
it is not a successful original native HTTP response, task admission or oracle.
"""
from dataclasses import dataclass
from decimal import Decimal, localcontext
import copy
import hashlib
import re
import time
from urllib.parse import urlencode
import xml.etree.ElementTree as ET
from . import map_native_request_bounds as artifact
from .map_osm_native_reference import xml_objects

VERSION='map-native-full-bbox-union-v1'
NATIVE_NODE_CAP=50000
MAX_REQUESTS=255
MAX_DEPTH=20
MAX_UNION_OBJECTS=500000
MAX_NATIVE_CHILD_BYTES=64*1024*1024
# The recorded six native children total 89,492,279 bytes; the complete
# adapted union needs its own bound, independent of any one native response.
MAX_UNION_BYTES=128*1024*1024
CAP_ERROR=re.compile(rb'^You requested too many nodes \(limit is 50000\)\. Either request a smaller area, or use planet\.osm\s*$')

@dataclass(frozen=True)
class Response:
    status:int
    content_type:str
    body:bytes

class NativeBatchError(ValueError):
    def __init__(self,message,ledger):
        super().__init__(message)
        self.ledger=copy.deepcopy(ledger)
        value=str(message).lower()
        # Controlled categories only; never publish arbitrary HTTP/XML text.
        if 'union exceeds compatibility byte budget' in value:self.reason_code='union_byte_budget'
        elif 'inspection budget' in value:self.reason_code='object_budget'
        elif 'deadline' in value:self.reason_code='absolute_deadline'
        elif 'request budget' in value:self.reason_code='request_budget'
        elif 'depth' in value:self.reason_code='subdivision_depth'
        elif 'duplicate id' in value:self.reason_code='conflicting_native_object'
        elif 'transport failed' in value:self.reason_code='native_transport'
        elif 'xml' in value:self.reason_code='native_xml_validation'
        else:self.reason_code='native_batch_validation' 


def digest(value):return hashlib.sha256(value).hexdigest()

def exact_bounds(values):
    # Reuse the reviewed full request-bbox adapter; node/XML coordinates keep
    # native seven-decimal validation in their own independent parser.
    result=artifact.bbox(values)
    if artifact.bbox_area(result)>Decimal('0.25'):
        raise ValueError('Original bbox exceeds the unchanged native map area limit')
    return result


def split_bounds(bounds):
    west,south,east,north=map(Decimal,exact_bounds(bounds))
    with localcontext()as ctx:
        ctx.prec=80
        if east-west>=north-south:
            middle=(west+east)/2
            cells=[(west,south,middle,north),(middle,south,east,north)]
        else:
            middle=(south+north)/2
            cells=[(west,south,east,middle),(west,middle,east,north)]
    result=[exact_bounds([format(v,'f')for v in cell])for cell in cells]
    # The native boundary predicate uses Float64 scaled coordinates. Refuse
    # subdivisions indistinguishable by that actual native representation.
    if any(float(Decimal(c[2]))<=float(Decimal(c[0]))or float(Decimal(c[3]))<=float(Decimal(c[1]))for c in result):
        raise ValueError('Native floating bbox cannot be subdivided further')
    return result


def coverage_checks(original,cells):
    original=exact_bounds(original);root=list(map(Decimal,original))
    try:
        cells=[exact_bounds(c)for c in cells];boxes=[list(map(Decimal,c))for c in cells]
    except(ValueError,TypeError):return {'all_cells_within_original':False,'interiors_disjoint':False,'exact_original_area_covered':False}
    inside=bool(boxes)and all(root[0]<=b[0]<b[2]<=root[2]and root[1]<=b[1]<b[3]<=root[3]for b in boxes)
    disjoint=all(min(a[2],b[2])<=max(a[0],b[0])or min(a[3],b[3])<=max(a[1],b[1])for i,a in enumerate(boxes)for b in boxes[i+1:])
    with localcontext()as ctx:
        ctx.prec=600
        area=sum(((b[2]-b[0])*(b[3]-b[1])for b in boxes),Decimal(0))
        expected=(root[2]-root[0])*(root[3]-root[1])
    return {'all_cells_within_original':inside,'interiors_disjoint':disjoint,'exact_original_area_covered':inside and disjoint and area==expected}


def semantic_xml_element(item):
    children=[]
    for child in item:
        children.append((child.tag,tuple(sorted(child.attrib.items()))))
    # XML tag ordering is semantically irrelevant. Ordered nd/member entries
    # remain ordered; every object attribute, version and reference is retained.
    ordered=[v for v in children if v[0]!='tag']
    tags=sorted(v for v in children if v[0]=='tag')
    return tuple(sorted(item.attrib.items())),tuple(ordered),tuple(tags)


def union_xml(original,leaves):
    bounds=exact_bounds(original)
    if not leaves or not all(coverage_checks(bounds,[b for b,_ in leaves]).values()):
        raise ValueError('Native child rectangles do not exactly cover original bbox')
    objects={};root_attributes=None
    for cell,payload in leaves:
        parsed,_=xml_objects(payload)
        if parsed['bounds']!=artifact.native_xml_bbox(cell):raise ValueError('Actual native child XML bounds differ from request')
        root=ET.fromstring(payload)
        if root_attributes is None:root_attributes=dict(root.attrib)
        elif dict(root.attrib)!=root_attributes:raise ValueError('Native child XML root protocol changed')
        for item in root:
            if item.tag=='bounds':continue
            key=(item.tag,item.attrib['id']);semantic=semantic_xml_element(item)
            if key in objects and objects[key][0]!=semantic:
                raise ValueError('Native duplicate ID changed version, attributes, tags or ordered references')
            # Each root is privately parsed here. Retain its element directly;
            # do not eagerly deepcopy every already-known duplicate object.
            if key not in objects:objects[key]=(semantic,item)
            if len(objects)>MAX_UNION_OBJECTS:raise ValueError('Complete native union exceeds independent compatibility inspection budget')
    # Do not retain a native generator on an adapted response. Native children
    # and original400 remain separately recorded; downloads are not intercepted.
    root_attributes=dict(root_attributes or {});root_attributes['generator']=VERSION
    merged=ET.Element('osm',root_attributes)
    ET.SubElement(merged,'bounds',dict(zip(artifact.COORD_NAMES,artifact.native_xml_bbox(bounds))))
    for kind in('node','way','relation'):
        for key in sorted((k for k in objects if k[0]==kind),key=lambda v:int(v[1])):merged.append(objects[key][1])
    payload=ET.tostring(merged,encoding='utf-8',xml_declaration=True)
    if len(payload)>MAX_UNION_BYTES:raise ValueError('Complete native union exceeds compatibility byte budget')
    # Existing native parser validates each actual child and its way refs.
    # Duplicating nodes cannot leave a way without a member in their full union.
    ids={key[1]for key in objects if key[0]=='node'}
    if any(nd.attrib['ref']not in ids for key,(_,item)in objects.items()if key[0]=='way'for nd in item.findall('nd')):
        raise ValueError('Complete union lost native way member nodes')
    counts={k:sum(key[0]==k for key in objects)for k in('node','way','relation')}
    return payload,{'version':VERSION,'counts':counts,'sha256':digest(payload),'bytes':len(payload),
        'bounds':list(bounds),'serialized_native_xml_bounds':list(artifact.native_xml_bbox(bounds)),
        'coverage':coverage_checks(bounds,[b for b,_ in leaves]),'native_children':len(leaves),
        'all_native_child_http200_required':True,'native_single_request_success':False,
        'native_node_limit_changed':False,'artifact_download_completed':False,'task_admitted':False}


def fetch_complete(original,fetcher,*,deadline,initial_response=None,preserve=None,max_requests=MAX_REQUESTS):
    """fetcher(bounds, remaining) must return actual same-origin native response.

    A callback preserves every child bytes/status before validation. The caller
    supplies one absolute deadline; retries do not renew it. No alternate URL,
    full-db serving, fake empty payload or zoom occurs here.
    """
    bounds=exact_bounds(original);ledger=[];leaves=[]
    if type(max_requests)is not int or not 1<=max_requests<=MAX_REQUESTS:raise ValueError('Bounded native request budget required')
    def visit(cell,depth,preloaded=None):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise NativeBatchError('Native full-bbox absolute deadline exhausted',ledger)
        if len(ledger)>=max_requests:raise NativeBatchError('Native full-bbox request budget exhausted',ledger)
        start=time.monotonic()
        item={'bounds':list(cell),'http_status':None,'depth':depth,'status':'started','seconds':None}
        ledger.append(item);index=len(ledger)-1
        if preserve is not None:preserve(index,item,None)
        try:response=preloaded if preloaded is not None else fetcher(cell,remaining)
        except Exception as exc:
            item.update(status='transport_failed',failure_type=type(exc).__name__,seconds=time.monotonic()-start)
            if preserve is not None:preserve(index,item,None)
            raise NativeBatchError('Actual native child transport failed before response',ledger)from exc
        if not isinstance(response,Response)or type(response.status)is not int or not isinstance(response.body,bytes)or not isinstance(response.content_type,str):
            item.update(status='invalid_response_schema',seconds=time.monotonic()-start)
            if preserve is not None:preserve(index,item,None)
            raise NativeBatchError('Actual native child response schema unavailable',ledger)
        item.update(status='response_received',http_status=response.status,content_type=response.content_type,
              bytes=len(response.body),sha256=digest(response.body),seconds=time.monotonic()-start)
        if preserve is not None:preserve(index,item,response.body)
        if time.monotonic()>deadline:raise NativeBatchError('Native full-bbox absolute deadline exhausted after response',ledger)
        if response.status==400 and CAP_ERROR.fullmatch(response.body):
            item['native_node_cap']=NATIVE_NODE_CAP
            if depth>=MAX_DEPTH:raise NativeBatchError('Native full-bbox subdivision depth exhausted',ledger)
            for child in split_bounds(cell):visit(child,depth+1)
            return
        if response.status!=200 or response.content_type.split(';',1)[0].strip().lower()not in('application/xml','text/xml'):
            raise NativeBatchError('Native bbox child is not actual HTTP200 XML; non-cap error preserved',ledger)
        try:
            parsed,_=xml_objects(response.body)
            if parsed['bounds']!=artifact.native_xml_bbox(cell):raise ValueError('Native child bbox changed')
        except(ValueError,ET.ParseError,TypeError,KeyError)as exc:
            raise NativeBatchError('Native HTTP200 child XML invalid: '+str(exc),ledger)from exc
        leaves.append((cell,response.body))
    try:
        visit(bounds,0,initial_response)
        payload,summary=union_xml(bounds,leaves)
    except NativeBatchError:raise
    except Exception as exc:raise NativeBatchError(str(exc),ledger)from exc
    summary.update(requests=ledger,native_parent_http_status=ledger[0]['http_status'],
        no_private_oracle_used_to_construct_union=True,each_child_uses_original_native_endpoint=True)
    return payload,summary


def child_api_path(bounds):return '/api/0.6/map?'+urlencode({'bbox':','.join(exact_bounds(bounds))})

"""Independent read-only full-bbox oracle; never used to serve browser objects.

This reference reads the original complete node selection and the native way /
parent-relation expansion without imposing the HTTP node cap on a private DB
oracle. Actual API requests STILL use the installed50K cap. Inspection budgets
are separate and exhaustion remains unknown, never an incomplete true result.
"""
import hashlib,json,math,re
from decimal import Decimal
from pathlib import Path
import xml.etree.ElementTree as ET
from . import map_native_request_bounds as artifact
from . import map_osm_native_reference as native
from .map_native_bbox_batch import VERSION,MAX_UNION_OBJECTS,MAX_UNION_BYTES,exact_bounds
from .io_utils import atomic_write_json


def full_reference_program(bounds,filename):
    bounds=exact_bounds(bounds)
    # The original direct-export generator validates stored-node precision.
    # Leaflet request bounds use full floating precision; only substitute the
    # two validated Ruby literals after obtaining the unchanged native template.
    # This placeholder is never executed or used for any object selection.
    placeholder=('0','0','1','1')
    program=native.rails_reference_program(placeholder,filename)
    old_bounds=json.dumps(','.join(placeholder))
    if program.count(old_bounds)!=2:
        raise ValueError('Pinned native reference bounds locations changed')
    program=program.replace(old_bounds,json.dumps(','.join(bounds)))
    old='nodes = Node.bbox(bounds).where(:visible => true).includes(:node_tags).limit(Settings.max_number_of_nodes + 1).to_a'
    if old not in program:raise ValueError('Pinned native independent selection changed')
    program=program.replace(old,'nodes = Node.bbox(bounds).where(:visible => true).includes(:node_tags).limit('+str(MAX_UNION_OBJECTS+1)+').to_a')
    old='raise "Native bbox node limit exceeded" if initial_node_ids.length > Settings.max_number_of_nodes'
    if old not in program:raise ValueError('Pinned native independent selection budget changed')
    program=program.replace(old,'raise "Complete private reference inspection budget exceeded" if initial_node_ids.length > '+str(MAX_UNION_OBJECTS))
    # Only private materialization budget differs; native controller and
    # Settings.max_number_of_nodes remain exactly unchanged and still checked
    # by every real child HTTP request.
    program=program.replace('> '+str(artifact.MAX_OBJECTS),'> '+str(MAX_UNION_OBJECTS))
    return program


def capture_full_reference(site,bounds,directory,name):
    if not re.fullmatch('[a-z0-9_-]+',name):raise ValueError('Bounded reference label required')
    filename='osm-expanded-'+name+'.json';state=site.state/'frontend';program=state/('full-bbox-reference-'+name+'.rb')
    program.write_text(full_reference_program(bounds,filename))
    command=list(site.rails_command);command=command[:command.index('server')]+['runner','/state/'+program.name]
    site.run(command,'full_bbox_independent_reference_'+name,180)
    value=json.loads((state/filename).read_text());database_objects(value,bounds)
    atomic_write_json(Path(directory)/(name+'-full-independent-database.json'),value)
    return value


def _tags(value):return native._tags(value)

def database_objects(value,bounds):
    bounds=exact_bounds(bounds)
    if not isinstance(value,dict)or set(value)!={'version','bounds','initial_node_ids','nodes','ways','relations'}or value['version']!=native.VERSION or exact_bounds(value['bounds'])!=bounds:
        raise ValueError('Exact complete independently selected native reference required')
    objects={k:{}for k in('node','way','relation')}
    for plural,kind in [('nodes','node'),('ways','way'),('relations','relation')]:
        if not isinstance(value[plural],list):raise ValueError('Complete native object lists required')
        for row in value[plural]:
            fields={'id','version','tags'}|({'lat','lon'}if kind=='node'else{'nodes'}if kind=='way'else{'members'})
            if not isinstance(row,dict)or set(row)!=fields:raise ValueError('Native reference schema changed')
            ident=artifact.positive_id(row['id']);record={'version':artifact.positive_id(row['version']),'tags':_tags(row['tags'])}
            if ident in objects[kind]:raise ValueError('Duplicate independent native ID')
            if kind=='node':
                record.update(lat=artifact.coordinate(row['lat']),lon=artifact.coordinate(row['lon']))
                if not -90<=Decimal(record['lat'])<=90:raise ValueError('Native node latitude invalid')
            elif kind=='way':
                if not isinstance(row['nodes'],list)or not row['nodes']:raise ValueError('Complete ordered native way nodes required')
                record['nodes']=[artifact.positive_id(v)for v in row['nodes']]
            else:
                if not isinstance(row['members'],list):raise ValueError('Complete native relation members required')
                members=[]
                for m in row['members']:
                    if not isinstance(m,dict)or set(m)!={'type','ref','role'}or m['type']not in objects or not isinstance(m['role'],str):raise ValueError('Native relation member malformed')
                    members.append(dict(m,ref=artifact.positive_id(m['ref'])))
                record['members']=members
            objects[kind][ident]=record
            if sum(len(v)for v in objects.values())>MAX_UNION_OBJECTS:raise ValueError('Private full reference inspection budget exceeded')
    initial=value['initial_node_ids']
    if not isinstance(initial,list)or not initial or len(initial)!=len(set(initial))or any(artifact.positive_id(v)not in objects['node']for v in initial):raise ValueError('Complete nonempty initial native bbox nodes required')
    if any(n not in objects['node']for w in objects['way'].values()for n in w['nodes']):raise ValueError('Independent native way lost a member node')
    # Native Node.bbox scales Float64 bounds in OSM.sql_for_area; preserve this
    # exact predicate instead of falsely excluding a native boundary node via
    # higher-precision Decimal-only containment.
    west,south,east,north=[float(Decimal(v))*10000000 for v in bounds]
    if any(not(west<=int(Decimal(objects['node'][i]['lon'])*10000000)<=east and south<=int(Decimal(objects['node'][i]['lat'])*10000000)<=north)for i in initial):raise ValueError('Independent initial node lies outside the actual native scaled predicate')
    return objects,sorted(initial)


def envelope_objects(payload):
    if not isinstance(payload,bytes)or not 1<=len(payload)<=MAX_UNION_BYTES or b'<!DOCTYPE'in payload.upper()or b'<!ENTITY'in payload.upper():raise ValueError('Complete adapted envelope invalid/over budget')
    root=ET.fromstring(payload)
    if root.tag!='osm'or root.attrib.get('version')!='0.6'or root.attrib.get('generator')!=VERSION:raise ValueError('Explicit adapted native union required')
    bounds_nodes=root.findall('bounds')
    if len(bounds_nodes)!=1:raise ValueError('One adapted serialized bounds required')
    bounds=artifact.bbox([bounds_nodes[0].attrib.get(n)for n in artifact.COORD_NAMES]);rows={'node':[],'way':[],'relation':[]}
    for item in root:
        if item.tag=='bounds':continue
        if item.tag not in rows:raise ValueError('Unexpected native union object')
        row={'id':item.attrib.get('id'),'version':item.attrib.get('version'),'tags':{}}
        allowed={'tag','nd'}if item.tag=='way'else{'tag','member'}if item.tag=='relation'else{'tag'}
        for c in item:
            if c.tag not in allowed:raise ValueError('Unexpected native union member')
            if c.tag=='tag':
                k,v=c.attrib.get('k'),c.attrib.get('v')
                if not isinstance(k,str)or not k or not isinstance(v,str)or k in row['tags']:raise ValueError('Native union tag invalid')
                row['tags'][k]=v
        if item.tag=='node':row.update(lat=item.attrib.get('lat'),lon=item.attrib.get('lon'))
        elif item.tag=='way':row['nodes']=[c.attrib.get('ref')for c in item.findall('nd')]
        else:row['members']=[dict(c.attrib)for c in item.findall('member')]
        rows[item.tag].append(row)
    # Reuse strict object validation without inventing initial IDs: below
    # compare_database_union gets them exclusively from independent native DB.
    return bounds,rows


def compare_database_union(payload,original_bounds,database):
    bounds=exact_bounds(original_bounds);expected,initial=database_objects(database,bounds);serialized,rows=envelope_objects(payload)
    synthetic={'version':native.VERSION,'bounds':list(bounds),'initial_node_ids':initial,'nodes':rows['node'],'ways':rows['way'],'relations':rows['relation']}
    try:actual,_=database_objects(synthetic,bounds)
    except ValueError as exc:return {'version':VERSION,'passed':False,'checks':{'all_native_objects_valid':False},'failure_type':type(exc).__name__,'api_payload_constructed_expected_reference':False}
    checks={'serialized_original_bounds':serialized==artifact.native_xml_bbox(bounds)}
    for kind in expected:
        checks[kind+'_ids']=set(expected[kind])==set(actual[kind]);checks[kind+'_versions_geometry_tags_members']=expected[kind]==actual[kind]
    return {'version':VERSION,'passed':all(checks.values()),'checks':checks,'counts':{k:len(v)for k,v in actual.items()},'initial_native_bbox_nodes':len(initial),'api_payload_constructed_expected_reference':False,'original_full_bbox_preserved':True,'native_api_cap_changed':False,'native_single_map_http200_claim':False,'payload_sha256':hashlib.sha256(payload).hexdigest()}


def compare_database_native_200(payload,original_bounds,database):
    """Compare an actual unchanged native200XML to a separate full DB oracle.

    Unlike adapted envelopes this branch retains the native generator and
    parser. Its bounds selection still uses the actual native scaled predicate.
    No response is created or served by the reference.
    """
    bounds=exact_bounds(original_bounds);expected,_=database_objects(database,bounds)
    parsed,actual=native.xml_objects(payload)
    checks={'serialized_original_bounds':parsed['bounds']==artifact.native_xml_bbox(bounds)}
    for kind in expected:
        checks[kind+'_ids']=set(expected[kind])==set(actual[kind])
        checks[kind+'_versions_geometry_tags_members']=expected[kind]==actual[kind]
    return {'version':VERSION,'passed':all(v is True for v in checks.values()),
            'checks':checks,'payload_sha256':hashlib.sha256(payload).hexdigest(),
            'api_payload_constructed_expected_reference':False,
            'original_full_bbox_preserved':True,'native_api_cap_changed':False,
            'native_single_map_http200_claim':True}

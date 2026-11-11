"""Typed native documentation lists; never follow external resource links."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from .map_metadata_query import verify_sources
from .query_record_sets import canonical_records

SHAPES = {'chapters': {'name': 'string'},
          'download_sources': {'name': 'string', 'description': 'string'}}
PATHS = {'chapters': '/communities', 'download_sources': '/export'}


def normalize(text):
    return ' '.join(text.split())


def captured_values(doc, kind):
    if doc.get('http_status') != 200 or doc.get('requested_path') != PATHS[kind]:
        raise ValueError('Missing native documentation page')
    lines = [s.strip() for s in doc['body'].splitlines() if s.strip()]
    if kind == 'chapters':
        start = lines.index('The following communities are formally established as Local Chapters:') + 1
        end = lines.index('Other Groups', start)
        rows = [{'name': normalize(name)} for name in lines[start:end]]
        # Independent link names must cover the same list in the recorded page.
        links = {normalize(r['text']) for r in doc['links']}
        if any(r['name'] not in links for r in rows):
            raise ValueError('Chapter body lacks matching native links')
    else:
        rows = []
        for name in ('Overpass API', 'Planet OSM', 'Geofabrik Downloads', 'Other Sources'):
            if lines.count(name) != 1 or sum(r['text'].strip() == name for r in doc['links']) != 1:
                raise ValueError('Download-source identity absent or ambiguous')
            rows.append({'name': name, 'description': normalize(lines[lines.index(name)+1])})
    canonical_records(rows, SHAPES[kind])
    if not rows: raise ValueError('Empty native documentation list')
    return {'items': rows}


def validate(q):
    if q.get('family') != 'map_documentation' or q.get('kind') not in SHAPES:
        raise ValueError('Unsupported documentation query')
    kind = q['kind']
    if q.get('reference_path') != PATHS[kind] or q.get('fields') != {'items': 'record_set'} or q.get('record_fields') != {'items': SHAPES[kind]}:
        raise ValueError('Unexpected documentation scope/schema')
    canonical_records(q['reference_values']['items'], SHAPES[kind])
    if not q['reference_values']['items']:
        raise ValueError('Empty documentation reference')
    proofs = q.get('reference_evidence', [])
    if len(proofs) != 2 or len({r['file'] for r in proofs}) != 2:
        raise ValueError('Two independent native captures required')


def reference(site, q):
    validate(q); verify_sources(site, q)
    for evidence in q['reference_evidence']:
        raw = Path(evidence['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != evidence['sha256']:
            raise ValueError('Recorded documentation evidence changed')
        if captured_values(json.loads(raw), q['kind']) != q['reference_values']:
            raise ValueError('Reference differs from the native captured list')
    return {'object_id': 'map-documentation:'+q['kind'], 'values': q['reference_values'],
            'source_evidence': q['source_evidence'], 'reference_evidence': q['reference_evidence']}


def ui_values(page, q, *, evidence=None):
    validate(q)
    u = urlsplit(page.url)
    page.goto(u.scheme+'://'+u.netloc+q['reference_path'], wait_until='domcontentloaded', timeout=60000)
    if urlsplit(page.url).path != q['reference_path']:
        raise ValueError('Documentation redirected to another page')
    if q['kind'] == 'chapters':
        heading = page.get_by_role('heading', name='Local Chapters', exact=True)
        if heading.count() != 1 or not heading.is_visible(): raise ValueError('Chapter section unavailable')
        rows = heading.evaluate('''h => {
          const rows=[];
          for(let e=h.nextElementSibling;e && !/^H[12]$/.test(e.tagName);e=e.nextElementSibling){
            if(e.tagName==='UL')for(const li of e.querySelectorAll(':scope > li'))
              if(li.getClientRects().length && getComputedStyle(li).visibility!=='hidden') rows.push({name:li.innerText});
          }return rows;
        }''')
    else:
        dl = page.locator('.export_form dl')
        dl.wait_for(state='visible', timeout=15000)
        if dl.count() != 1: raise ValueError('Download list missing or ambiguous')
        rows = dl.locator('dt').evaluate_all('''es => es.filter(e=>e.getClientRects().length).map(e=>({
          name:e.innerText,description:e.nextElementSibling?.tagName==='DD'?e.nextElementSibling.innerText:null}))''')
    if not rows or any(any(not isinstance(v, str) or not v.strip() for v in row.values()) for row in rows):
        raise ValueError('Native documentation list incomplete')
    rows = [{k: normalize(v) for k, v in row.items()} for row in rows]
    canonical_records(rows, SHAPES[q['kind']])
    if evidence is not None:
        evidence.append({'path': q['reference_path'], 'items': rows, 'external_links_followed': False})
    return {'items': rows}

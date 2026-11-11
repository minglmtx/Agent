"""Declared material creation: native saved formatting and local image bytes.

Task-specific values live in the explicit task contract. This module never
navigates the actor browser, repairs its content, or contacts an external host.
"""
import hashlib,json,re,subprocess
from pathlib import Path
from urllib.parse import unquote,urlsplit
from bs4 import BeautifulSoup
from .admin_creation_guard import creation_checks

VERSION='admin-material-creation-v1'

def material_definition(source):
    path=Path(__file__).resolve().parents[2]/'configs/admin-material-creation.json'
    definition=json.loads(path.read_text())
    return definition if definition['source_task_id']==source else None

def fixture_source(source):
    definition=material_definition(source)
    return definition['fixture_source_id'] if definition else source

def bind_creation(row,state,definition):
    from .admin_pilot import BindingError
    if (row.get('kind')!='derived' or row.get('runtime_task_id')!=definition['runtime_task_id']
            or row.get('goal')!=definition['goal'] or row.get('source_goal')!=definition['source_goal']):
        raise BindingError('Material creation requires exact public derived contract')
    material=definition['material']
    if state.get('record_errors') or not isinstance(state.get('records',{}).get('product'),list):
        raise BindingError('Material creation needs complete initial product inventory')
    if any(p['sku']==material['sku'] for p in state['records']['product']):
        raise BindingError('Creation SKU already exists at reset')
    if hashlib.sha256(Path(material['image']).read_bytes()).hexdigest()!=material['image_sha256']:
        raise BindingError('Declared upload material changed')
    return dict(source_task_id=row['source_task_id'],runtime_task_id=row['runtime_task_id'],
        goal=row['goal'],kind='derived',scope_id=0,start_path='/catalog/product/new/set/4/type/simple/',
        status='ready_for_single_attempt',evaluator_version=VERSION,not_formal_training_admission=True,
        spec=dict(kind='material_product_creation',material=material,fixture_source_id=definition['fixture_source_id'],
                  upload_resources=[dict(path=material['image'],sha256=material['image_sha256'])]))

def description_images(description):
    """Only actual image tags count, not prose containing a media URL."""
    dom=BeautifulSoup(description,'html.parser')
    result=[]
    for image in dom.select('img[src]'):
        src=image['src'].strip()
        match=re.fullmatch(r'\{\{media\s+url\s*=\s*[\"\']?([^\"\'{}]+?)[\"\']?\s*\}\}',src)
        if match:result.append(match.group(1).strip());continue
        url=urlsplit(src)
        if not url.scheme and not url.netloc and url.path.startswith('/media/') and not url.query and not url.fragment:
            result.append(url.path[len('/media/'):])
        else:result.append(None)  # Remote/data URLs never trigger a fetch.
    return result

def local_image_receipts(description,media_root):
    base=Path(media_root).resolve();receipts=[]
    for raw in description_images(description):
        if raw is None:
            receipts.append(dict(reference=raw,status='nonlocal'));continue
        relative=unquote(raw)
        path=Path(relative)
        if path.is_absolute() or '..' in path.parts or '\\' in relative or '\x00' in relative:
            receipts.append(dict(reference=raw,status='outside_media'));continue
        target=(base/path).resolve()
        if not target.is_relative_to(base):
            receipts.append(dict(reference=raw,status='outside_media'));continue
        if not target.exists():
            receipts.append(dict(reference=raw,status='missing'));continue
        if not target.is_file() or target.stat().st_size>32*1024*1024:
            receipts.append(dict(reference=raw,status='invalid_image_file'));continue
        receipts.append(dict(reference=raw,status='read',sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    return receipts

def formatting_checks(description,rendered,material):
    saved=BeautifulSoup(description,'html.parser');dom=BeautifulSoup(rendered,'html.parser')
    heading=any(x.get_text(' ',strip=True)==material['heading'] for x in dom.select('strong,b'))
    bullets=any([x.get_text(' ',strip=True)for x in ul.select(':scope > li')]==material['bullets']for ul in dom.select('ul'))
    return dict(saved_pagebuilder_content=bool(saved.select('[data-content-type]')),
                native_bold_heading=heading,native_requested_bullets=bullets)

def collect_creation_evidence(binding,after,site,project,root,destination):
    """Bounded read-only collector; failure is a runtime error, never reward 0."""
    material=binding['spec']['material'];products=[p for p in after['records']['product']if p['sku']==material['sku']]
    if len(products)!=1:return dict(version=VERSION,target_count=len(products))
    target=products[0];description=target.get('description') or ''
    from .io_utils import atomic_write_json
    inputs=Path(destination)/'material-render-input.json';atomic_write_json(inputs,{'saved':description})
    command=['apptainer','exec','--cleanenv','--containall','--no-home','--no-mount','bind-paths,hostfs,cwd','--pwd','/',
        '--bind',str(Path(project)/'cluster/admin-pagebuilder-render.php')+':/native-filter.php:ro',
        '--bind',str(inputs)+':/inputs.json:ro',str(Path(root)/'containers/webarena/shopping-admin.sif'),
        'php','/native-filter.php','/inputs.json']
    response=subprocess.run(command,capture_output=True,text=True,timeout=30)
    if response.returncode:raise RuntimeError('Native PageBuilder renderer failed: '+response.stderr[-800:])
    rendered=json.loads(response.stdout)
    if rendered['source_sha256']!=material['native_renderer_sha256'] or rendered['database_calls']!=0:
        raise RuntimeError('Native PageBuilder renderer version differs')
    receipts=local_image_receipts(description,Path(site.temp.name)/'webarena-admin/app/pub/media')
    evidence=dict(version=VERSION,target_count=1,entity_id=target['entity_id'],description_sha256=hashlib.sha256(description.encode()).hexdigest(),
                  native_renderer=rendered,images=receipts)
    atomic_write_json(Path(destination)/'material-creation-evidence.json',evidence)
    return evidence

def creation_evaluation(binding,before,after,page):
    material=binding['spec']['material'];checks=creation_checks(before,after,material)
    if not checks.get('one_new_target'):return checks
    target=next(p for p in after['records']['product']if p['sku']==material['sku']);description=target.get('description') or ''
    proof=page['material_creation']
    if (proof['version']!=VERSION or proof['target_count']!=1 or str(proof['entity_id'])!=str(target['entity_id'])
            or proof['description_sha256']!=hashlib.sha256(description.encode()).hexdigest()):
        raise ValueError('Saved-description evidence mismatch')
    native=proof['native_renderer']
    if native['source_sha256']!=material['native_renderer_sha256'] or native['database_calls']!=0:
        raise ValueError('Wrong native renderer')
    checks.update(formatting_checks(description,native['rendered']['saved'],material))
    images=proof['images']
    if [r['reference']for r in images]!=description_images(description):
        raise ValueError('Image evidence does not match saved references')
    checks['persisted_supplied_image']=any(r['status']=='read' and r['sha256']==material['image_sha256']for r in images)
    return checks

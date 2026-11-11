"""Generic final-state native GitLab content completion and admission.

Private immutable repository/profile references are loaded from a bound file.
Only actual public terminal DOM/image response digests enter saved evidence;
expected Git bodies/paths/answers are never returned in feedback or prompts.
No navigation, scrolling, actor tools, or model calls are performed here.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote,urlsplit

from .gitlab_profile_identity import READ as PROFILE_READ, profile_checks
from .gitlab_repository import READ as REPOSITORY_READ, read_repository_page, verify_repository_reference
from .gitlab_rendered_markdown_v4 import rendered_markdown_checks
from .gitlab_native_source_lines import READ as SOURCE_READ

VERSION='gitlab-native-content-v1'
ADMISSION_VERSION=VERSION+'-normal-two-fresh'
KINDS={'repository_document','public_user_profile','loaded_repository_image'}
DOCUMENT_CATALOG_SCOPES={'markdown_documents','regular_files'}


def document_catalog_scope(reference):
    """Retain both original catalog formats without changing their pinned bytes.

    Early references contain every Markdown document; the source-document
    constructor also includes regular files such as .11tydata.js. Explicit
    scope takes precedence. Existing references with a non-Markdown object
    use the complete regular-file scope; old Markdown catalogs stay readable.
    """
    scope=reference.get('document_catalog_scope')
    if scope is None:
        scope=('regular_files'if any(not row['path'].lower().endswith(('.md','.markdown'))
                for row in reference['documents'])else'markdown_documents')
    if not isinstance(scope,str)or scope not in DOCUMENT_CATALOG_SCOPES:
        raise ValueError('Supported complete document catalog scope required')
    if scope=='markdown_documents'and any(not row['path'].lower().endswith(('.md','.markdown'))
            for row in reference['documents']):
        raise ValueError('Non-Markdown object in Markdown document catalog')
    return scope


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def family(contract):
    completion=contract.get('completion',{})
    return completion.get('family')=='gitlab_native_content'


def _path(value):
    if not isinstance(value,str)or not value or value.startswith('/')or any(x in('.','..','')for x in value.split('/'))or any(x in value for x in ('\0','\\')):
        raise ValueError('Invalid native repository path')
    return value


def _repository(reference):
    if not isinstance(reference,dict)or type(reference.get('project_id'))is not int or reference['project_id']<=0:
        raise ValueError('Pinned native repository identity required')
    _path(reference.get('project'))
    if not re.fullmatch('[A-Za-z0-9_.][A-Za-z0-9_./-]*',reference.get('ref',''))or '..'in reference['ref']:
        raise ValueError('Pinned native repository revision required')
    if not re.fullmatch('[0-9a-f]{40}',reference.get('head','')):
        raise ValueError('Immutable native repository head required')
    return reference


def validate_reference(reference):
    if not isinstance(reference,dict)or reference.get('version')!=VERSION or reference.get('kind')not in KINDS:
        raise ValueError('Versioned native content reference required')
    kind=reference['kind']
    if kind=='public_user_profile':
        r=reference.get('namespace')
        if not isinstance(r,dict)or r.get('type')!='User'or type(r.get('id'))is not int or r['id']<=0 or type(r.get('owner_id'))is not int or r['owner_id']<=0:
            raise ValueError('Independent native User namespace required')
        if any(not isinstance(r.get(k),str)or not r[k]for k in ('owner_username','owner_name','route'))or r['route']!=r['owner_username']:
            raise ValueError('Native public user namespace route must agree')
        return reference
    repository=_repository(reference.get('repository'))
    if kind=='repository_document':
        if reference.get('native_document_views', 'rendered_markdown') not in ('rendered_markdown', 'rendered_markdown_or_exact_source_v2'):
            raise ValueError('Explicit supported native document view policy required')
        docs=reference.get('documents');subtree=reference.get('subtree')
        if not isinstance(docs,list)or not 1<=len(docs)<=64 or type(reference.get('accept_equivalent_rendered_content'))is not bool:
            raise ValueError('Finite pinned document catalog required')
        if subtree is not None:_path(subtree)
        if subtree is None and len(docs)!=1:raise ValueError('Exact document requires one native object')
        paths=[]
        for row in docs:
            _path(row.get('path'));paths.append(row['path'])
            if subtree is not None and not row['path'].startswith(subtree+'/'):raise ValueError('Document outside pinned subtree')
            if any(not re.fullmatch('[0-9a-f]{'+str(n)+'}',row.get(k,''))for k,n in [('object_sha',40),('source_text_sha256',64)]):raise ValueError('Pinned native document hashes required')
            body=row.get('source_text')
            if not isinstance(body,str)or not body.strip()or len(body.encode())>2000000 or hashlib.sha256(body.encode()).hexdigest()!=row['source_text_sha256']:
                raise ValueError('Private native document bytes differ from reference')
            blob=b'blob '+str(len(body.encode())).encode()+b'\0'+body.encode()
            if hashlib.sha1(blob).hexdigest()!=row['object_sha']:raise ValueError('Private native body and Git object disagree')
        if len(paths)!=len(set(paths)):raise ValueError('Duplicate pinned native document')
        if subtree is not None and reference.get('complete_pinned_subtree')is not True:
            raise ValueError('Complete immutable subtree catalog required')
        document_catalog_scope(reference)
    else:
        image=reference.get('image');dimensions=reference.get('dimensions')
        if not isinstance(image,dict):raise ValueError('Pinned native image required')
        _path(image.get('path'))
        if any(not re.fullmatch('[0-9a-f]{'+str(n)+'}',image.get(k,''))for k,n in [('object_sha',40),('bytes_sha256',64)]):raise ValueError('Native image hashes required')
        if not isinstance(dimensions,dict)or any(type(dimensions.get(k))is not int or dimensions[k]<=0 for k in ('width','height')):
            raise ValueError('Decoded native image dimensions required')
        if reference.get('accept_embedded_image')is not True:raise ValueError('Embedded native logo policy required')
    return reference


def validate(contract):
    if not family(contract)or contract.get('domain')!='gitlab':raise ValueError('Exact GitLab native content family required')
    spec=contract['completion'].get('gitlab_native_content')
    if not isinstance(spec,dict)or spec.get('version')!=VERSION or spec.get('kind')not in KINDS or not re.fullmatch('[0-9a-f]{64}',spec.get('reference_sha256','')):
        raise ValueError('Bound native content completion required')
    path=contract.get('native_content_reference_file')
    if not isinstance(path,str)or not Path(path).is_absolute():raise ValueError('Absolute private reference file required')
    if type(contract.get('allow_initial_success'))is not bool:raise ValueError('Explicit original-initial completion policy required')
    if contract.get('heldout_quarantine')is not False:raise ValueError('Heldout content task cannot be admitted')
    return spec


def load_reference(contract):
    spec=validate(contract);p=Path(contract['native_content_reference_file'])
    if p.stat().st_size>4000000:raise ValueError('Private native reference exceeds supported size')
    reference=json.loads(p.read_text());validate_reference(reference)
    if canonical_digest(reference)!=spec['reference_sha256']or reference['kind']!=spec['kind']:
        raise ValueError('Private native reference changed')
    return reference


def fingerprint(contract):
    validate(contract)
    return canonical_digest({k:contract.get(k)for k in ('task_id','source_task_id','domain','goal','start_path','completion',
        'native_content_reference_file','heldout_quarantine','completion_revision','allow_initial_success','initial_page_policy',
        'recorded_start_paths','source_trace_ids','control_target_path','wrong_target_path','control_error_path','control_login_path')})


def _git(site,reference,*args,binary=False):
    ident=reference['project_id'];digest=hashlib.sha256(str(ident).encode()).hexdigest()
    repo='/var/opt/gitlab/git-data/repositories/@hashed/'+digest[:2]+'/'+digest[2:4]+'/'+digest+'.git'
    return site.command(['/opt/gitlab/embedded/bin/git','--git-dir='+repo,*args],capture_output=True,text=not binary,timeout=40).stdout


def _subtree_documents(site,reference):
    repository=reference['repository'];subtree=reference['subtree']
    # NUL framing preserves spaces, Unicode and line breaks in native paths.
    # Match the source constructor's regular-file modes, excluding symlinks
    # and submodules rather than treating them as executable source documents.
    raw=_git(site,repository,'ls-tree','-r','-z',repository['head'],'--',subtree,binary=True)
    if not isinstance(raw,bytes)or (raw and not raw.endswith(b'\0')):
        raise RuntimeError('Incomplete native subtree listing')
    paths=[]
    for record in raw.split(b'\0'):
        if not record:continue
        try:
            metadata,path=record.split(b'\t',1)
            mode,kind,object_sha=metadata.split(b' ')
            path=path.decode('utf-8')
        except (ValueError,UnicodeDecodeError)as error:
            raise RuntimeError('Malformed native subtree listing')from error
        if mode not in (b'100644',b'100755'):continue
        if kind!=b'blob'or not re.fullmatch(b'[0-9a-f]{40}',object_sha)or not path.startswith(subtree+'/'):
            raise RuntimeError('Invalid native subtree source object')
        paths.append(path)
    if len(paths)!=len(set(paths)):raise RuntimeError('Duplicate native subtree source object')
    if document_catalog_scope(reference)=='markdown_documents':
        paths=[path for path in paths if path.lower().endswith(('.md','.markdown'))]
    return paths


def verify_reference(site,reference):
    validate_reference(reference)
    if reference['kind']=='public_user_profile':
        from .site_database import select_rows
        r=reference['namespace'];rows=select_rows(site,'SELECT n.id,n.name,n.path,n.type,n.owner_id,u.name AS owner_name,u.username AS owner_username,r.path AS route FROM namespaces n LEFT JOIN users u ON u.id=n.owner_id LEFT JOIN routes r ON r.source_type=\'Namespace\' AND r.source_id=n.id WHERE n.id='+str(r['id']))
        if len(rows)!=1:raise RuntimeError('Native namespace reference missing')
        actual=rows[0];actual['route']=actual.get('route')or actual.get('owner_username')
        if any(actual.get(k)!=r.get(k)for k in ('id','name','path','type','owner_id','owner_name','owner_username','route')):
            raise RuntimeError('Native namespace reference changed')
    else:
        repository=reference['repository']
        objects=reference['documents']if reference['kind']=='repository_document'else[reference['image']]
        for obj in objects:verify_repository_reference(site,{**repository,**obj,'kind':'blob'})
        if reference['kind']=='repository_document'and reference.get('subtree'):
            actual=_subtree_documents(site,reference)
            if set(actual)!={d['path']for d in reference['documents']}:raise RuntimeError('Native subtree catalog differs')
        if reference['kind']=='loaded_repository_image':
            body=_git(site,repository,'show',repository['head']+':'+reference['image']['path'],binary=True)
            if hashlib.sha256(body).hexdigest()!=reference['image']['bytes_sha256']:raise RuntimeError('Native image bytes changed')
    return {'version':VERSION,'private_reference_verified':True,'reference_sha256':canonical_digest(reference)}


READ=r'''() => {
 const shown=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
 const repository=('''+REPOSITORY_READ+r''')();repository.url=location.href;
 return {version:"'''+VERSION+r'''",url:location.href,repository,
   source_lines:('''+SOURCE_READ+r''')(),
   profile:('''+PROFILE_READ+r''')(),
   markdown_blocks:[...document.querySelectorAll('.file-content.md')].filter(shown).map(e=>e.outerHTML),
   images:[...document.querySelectorAll('main img,.file-content img,.blob-viewer img')].filter(shown).map(e=>({src:e.currentSrc||e.src,complete:e.complete,width:e.naturalWidth,height:e.naturalHeight,alt:e.alt})),
   capture_truncated:false};
}'''


def _raw_paths(reference):
    r=reference['repository'];path=reference['image']['path']
    return {'/'+r['project']+'/-/raw/'+ref+'/'+path for ref in (r['ref'],r['head'])}


IMAGE_READY=r'''() => {
 const repository=('''+REPOSITORY_READ+r''')();
 if(repository.loading)return false;
 if(!location.pathname.includes('/-/blob/'))return true;
 const shown=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 // Loading readiness and actual visible-image completion are separate checks.
 const images=[...document.querySelectorAll('.file-content img,.blob-viewer img')];
 const native=images.filter(e=>/\/-\/raw\//.test(new URL(e.currentSrc||e.src,location.href).pathname));
 if(native.length)return native.every(e=>e.complete);
 return repository.content.some(text=>text.trim());
}'''


def read_terminal(page,contract,*,site_origin):
    """Read current native DOM only. No private reference body enters evidence."""
    reference=load_reference(contract)
    if reference['kind']=='loaded_repository_image':
        # A native image blob may have no innerText. Use actual public image
        # completion, not the generic text-file ready predicate or private refs.
        from playwright.sync_api import TimeoutError as BrowserTimeout
        status='ready'
        try:page.wait_for_function(IMAGE_READY,timeout=8000,polling=100)
        except BrowserTimeout:status='content_wait_exhausted'
        ready={'url':page.url,'wait_status':status}
    else:ready=read_repository_page(page)
    state=page.evaluate(READ)
    if state['url']!=page.url or ready['url']!=state['url']:raise RuntimeError('Native terminal changed during capture')
    state['repository']['wait_status']=ready['wait_status']
    state['image_responses']=[]
    if reference['kind']=='loaded_repository_image':
        origin=urlsplit(site_origin)
        for image in state['images']:
            p=urlsplit(image['src'])
            if ((p.scheme,p.netloc)!=(origin.scheme,origin.netloc)or unquote(p.path)not in _raw_paths(reference)or p.query or p.fragment):continue
            if image['complete']is not True or image['width']<=0 or image['height']<=0:continue
            response=page.request.get(image['src'],timeout=15000,max_redirects=0)
            entry={'src':image['src'],'http_status':response.status,'bytes':None,'sha256':None}
            if response.status==200:
                body=response.body();entry.update(bytes=len(body),sha256=hashlib.sha256(body).hexdigest())
            state['image_responses'].append(entry)
    return state


def _document_checks(reference,state):
    repository=reference['repository'];native=state['repository'];path=unquote(urlsplit(state['url']).path).rstrip('/')
    candidates=[]
    for row in reference['documents']:
        routes={'/'+repository['project']+'/-/blob/'+ref+'/'+row['path']for ref in (repository['ref'],repository['head'])}
        if path in routes:candidates.append((row,True))
    if not candidates and reference['accept_equivalent_rendered_content'] and path.startswith('/'+repository['project']+'/'):
        candidates=[(row,False)for row in reference['documents']]
    blocks=state.get('markdown_blocks');html=blocks[0]if isinstance(blocks,list)and len(blocks)==1 else ''
    text_checks={k:False for k in ('complete_native_capture','native_markdown_block','frontmatter_complete','full_rendered_prose_equivalent','inline_reference_attributes_equivalent','image_elements_equivalent')}
    identity=False
    # Preserve the original source-document contract alongside Markdown.
    # The complete native line reader checks actual bytes on the exact route;
    # a partial capture, wrong file or rendered page cannot substitute for it.
    if reference.get('native_document_views') == 'rendered_markdown_or_exact_source_v2':
        from gitlab_native_read_completion import _source_checks
        for row, direct in candidates:
            if not direct:
                continue
            source = state.get('source_lines')
            code = source.get('blocks') if isinstance(source, dict) else None
            if not isinstance(code, list) or len(code) != 1 or code[0].get('path') != row['path']:
                continue
            spec = {'kind': 'source_blob', 'scope': 'whole_source', 'source_text': row['source_text'],
                    'repository': {**repository, **row, 'kind': 'blob'}}
            try:
                checks = _source_checks(spec, state)
            except (ValueError, KeyError, TypeError):
                continue
            if all(checks.values()):
                return {'requested_repository_identity': checks['requested_repository_identity'],
                        'requested_document_identity': checks['requested_native_blob_identity'],
                        'complete_native_source_content': checks['complete_native_source_content'],
                        'native_content_not_loading': native.get('loading') is False and native.get('wait_status') == 'ready'}
    for row,direct in candidates:
        for ref in (repository['ref'],repository['head']):
            actual=rendered_markdown_checks(row['source_text'],html,project=repository['project'],ref=ref,path=row['path'],capture_truncated=state.get('capture_truncated'))
            if all(actual.values()):text_checks=actual;identity=True;break
            if direct:text_checks=actual
        if identity:break
    return {'requested_repository_identity':str(repository['project_id'])in native.get('project_ids',[]),
        'requested_document_identity':identity,
        'native_content_not_loading':native.get('loading')is False and native.get('wait_status')=='ready',**text_checks}


def _image_checks(reference,state,site_origin):
    r=reference['repository'];origin=urlsplit(site_origin);paths=_raw_paths(reference)
    matching=[i for i in state.get('images',[])if isinstance(i,dict)and isinstance(i.get('src'),str)and
        (urlsplit(i['src']).scheme,urlsplit(i['src']).netloc)==(origin.scheme,origin.netloc)and unquote(urlsplit(i['src']).path)in paths and not urlsplit(i['src']).query and not urlsplit(i['src']).fragment]
    loaded=[i for i in matching if i.get('complete')is True and i.get('width')==reference['dimensions']['width']and i.get('height')==reference['dimensions']['height']]
    responses=state.get('image_responses',[])
    bytes_ok=any(x.get('http_status')==200 and x.get('sha256')==reference['image']['bytes_sha256']and x.get('src')in{i['src']for i in loaded}for x in responses if isinstance(x,dict))
    native=state['repository']
    return {'requested_repository_identity':str(r['project_id'])in native.get('project_ids',[]),
        'native_content_not_loading':native.get('loading')is False and native.get('wait_status')=='ready',
        'native_image_reference_present':bool(matching),'native_image_loaded_and_decoded':bool(loaded),'actual_served_bytes_match_reference':bytes_ok}


def evaluate(contract,page,*,site_origin):
    reference=load_reference(contract)
    required=('url','http_status','login_page','error_page')
    if not isinstance(page,dict)or any(k not in page for k in required)or not isinstance(page['url'],str)or (page['http_status']is not None and type(page['http_status'])is not int)or any(type(page[k])is not bool for k in ('login_page','error_page')):
        return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Incomplete native content terminal capture'}
    p=urlsplit(page['url']);origin=urlsplit(site_origin)
    checks={'correct_site':(p.scheme,p.netloc)==(origin.scheme,origin.netloc),
        'page_valid':type(page['http_status'])is int and 200<=page['http_status']<300 and not page['login_page']and not page['error_page']}
    # A recorded foreign/browser-error URL already proves this final state
    # cannot satisfy a local content task. Chromium error documents have no
    # HTTP response; do not invent one, or demand missing content from them.
    # In-site transport failures with no usable response remain unknown.
    if not checks['correct_site']:
        return {'version':VERSION,'status':'failure','reward':0.0,'checks':checks}
    if page['http_status']is None or not 200<=page['http_status']<500:
        return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Native content transport failure'}
    state=page.get('gitlab_native_content')
    if not isinstance(state,dict)or state.get('version')!=VERSION or state.get('url')!=page['url']:
        if all(checks.values()):return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Native content reader missing or changed page'}
        return {'version':VERSION,'status':'failure','reward':0.0,'checks':checks}
    if reference['kind']=='public_user_profile':
        try:content=profile_checks(reference['namespace'],state.get('profile'))
        except (ValueError,TypeError):content={k:False for k in ('current_profile_user_identity','current_profile_username','current_profile_name')}
    else:
        if not isinstance(state.get('repository'),dict):return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Native repository reader missing'}
        if state['repository'].get('url')!=state['url']:return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Native repository capture changed page'}
        r=state['repository']
        if not isinstance(r.get('project_ids'),list)or any(not isinstance(v,str)for v in r['project_ids'])or type(r.get('loading'))is not bool or r.get('wait_status')not in('ready','content_wait_exhausted'):
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Malformed native repository terminal capture'}
        if r['loading']or r['wait_status']!='ready' or state.get('capture_truncated')is not False:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Native content did not finish loading or capture is incomplete'}
        if reference['kind']=='loaded_repository_image'and any(not isinstance(state.get(k),list)for k in ('images','image_responses')):
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Native image reader incomplete'}
        content=_document_checks(reference,state)if reference['kind']=='repository_document'else _image_checks(reference,state,site_origin)
    checks.update(content);success=all(checks.values())
    return {'version':VERSION,'status':'success'if success else'failure','reward':float(success),'checks':checks}


FEEDBACK={'correct_site':'The final page is outside the configured website.',
    'page_valid':'The final page is a login or error page.',
    'requested_repository_identity':'The current content belongs to a different repository.',
    'requested_document_identity':'The requested document content is not complete on the final page.',
    'native_content_not_loading':'The native content is still loading or did not become readable.',
    'current_profile_user_identity':'The displayed profile identity does not match the task.',
    'current_profile_username':'The displayed profile username does not match the task.',
    'current_profile_name':'The displayed profile name does not match the task.',
    'native_image_reference_present':'The requested native image is not present on the final page.',
    'native_image_loaded_and_decoded':'The displayed image has not loaded and decoded correctly.',
    'actual_served_bytes_match_reference':'The displayed image response differs from the requested native image.'}
for _key in ('complete_native_capture','native_markdown_block','frontmatter_complete','full_rendered_prose_equivalent','inline_reference_attributes_equivalent','image_elements_equivalent'):
    FEEDBACK[_key]='The rendered document content is incomplete or differs from the requested document.'


def feedback(judgment):
    if judgment.get('version')!=VERSION:raise ValueError('Native content feedback version mismatch')
    if judgment['status']=='unknown':return {'status':'unknown','failures':['Native terminal evidence is incomplete; this attempt cannot be scored.']}
    return {'status':judgment['status'],'failures':list(dict.fromkeys(FEEDBACK[k]for k,v in judgment['checks'].items()if v is False))}


def _positive_names(reference):
    return ['positive_document_'+str(i)for i in range(len(reference['documents']))]if reference['kind']=='repository_document'else['positive']


def control_admission(contract,cases,*,site_origin):
    reference=load_reference(contract);positive=_positive_names(reference)
    names=['initial_no_op',*positive,'wrong_target','404','login']
    if any(k not in cases for k in names):return {'passed':False,'status':'missing_controls','checks':{}}
    judgments={k:evaluate(contract,cases[k],site_origin=site_origin)for k in names}
    from .site_start_state import valid_task_start
    from .site_navigation_rules import valid_initial_page
    valid=valid_task_start(contract,cases['initial_no_op'],site_origin=site_origin)
    initial=judgments['initial_no_op']['status'];allow=contract['allow_initial_success']
    expected=all(judgments[k]['status']=='success'for k in positive)and all(judgments[k]['status']=='failure'for k in ('wrong_target','404','login'))and initial in ('success','failure')and(allow or initial=='failure')
    passed=valid and expected and valid_initial_page(cases['wrong_target'],site_origin=site_origin)
    return {'passed':passed,'status':'passed'if passed else'contract_or_control_mismatch',
        'admission_version':ADMISSION_VERSION,'valid_initial_page':valid,'initial_goal_satisfied':initial=='success',
        'checks':{k:v['status']for k,v in judgments.items()}}


def require_admission(contract,proof):
    reference=load_reference(contract)
    if proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(contract)or proof.get('passed')is not True:
        raise ValueError('Bound normal native content proof required; capability is insufficient')
    cycles=proof.get('cycles')
    if not isinstance(cycles,list)or len(cycles)!=2:raise ValueError('Two fresh native control cycles required')
    if len({canonical_digest(c.get('initial_fingerprint'))for c in cycles})!=1 or not cycles[0].get('initial_fingerprint'):
        raise ValueError('Equal native fresh baselines required')
    instances=[c.get('fresh_instance_id')for c in cycles]
    if any(not isinstance(x,str)or not x for x in instances)or len(set(instances))!=2:
        raise ValueError('Independent fresh native instances required')
    expected=set(['initial_no_op',*_positive_names(reference),'wrong_target','404','login'])
    for cycle in cycles:
        if cycle.get('initial_fingerprint')!=cycle.get('final_fingerprint')or cycle.get('protected_records_unchanged')is not True or cycle.get('fresh_snapshot_instance')is not True:
            raise ValueError('Protected native references and fresh reset proof required')
        rows=[r for r in cycle.get('tasks',[])if r.get('task_id')==contract['task_id']]
        if len(rows)!=1 or rows[0].get('passed')is not True or rows[0].get('valid_initial_page')is not True or rows[0].get('private_reference_verified')is not True or rows[0].get('reference_sha256')!=canonical_digest(reference):
            raise ValueError('Actual original-start normal controls required')
        verdicts=rows[0].get('checks',{})
        if set(verdicts)!=expected or any(verdicts[k]!='success'for k in _positive_names(reference))or any(verdicts[k]!='failure'for k in ('wrong_target','404','login'))or verdicts['initial_no_op']not in('success','failure'):
            raise ValueError('Complete original-scope normal controls required')
        if not contract['allow_initial_success']and verdicts['initial_no_op']!='failure':raise ValueError('Original initial completion policy differs')
        if rows[0].get('initial_goal_satisfied')!=(verdicts['initial_no_op']=='success'):raise ValueError('Original initial verdict is inconsistent')
    return True

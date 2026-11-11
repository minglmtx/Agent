"""Pre-inference local executable-data closure, never evaluator or action repair."""
import hashlib,json
from pathlib import Path

GITLAB_FLAGS=('gitlab_persisted_goal','gitlab_boundary_goal','gitlab_explore_visit_goal','gitlab_native_read','gitlab_navigation_goal','gitlab_preference_goal_state',
              'gitlab_grouped_goal','preferences','clipboard','native_csv_export',
              'repository_download','project_creation','fork_creation','ref_creation','group_import')


def required(contract):
    wrapped = contract.get('public_completion', {}).get('original_contract')
    native_contract = wrapped if isinstance(wrapped, dict) else contract
    from lab_generate_skill.native_pdf_reader import required as pdf_required
    pdf_assets = ('configs/native-pdf-reader.json', 'src/lab_generate_skill/native_pdf_reader.py') if pdf_required(contract) else ()
    if (contract.get('domain') == 'shopping'
            and native_contract.get('completion', {}).get('family') == 'shopping_native_three'):
        return pdf_assets + ('src/lab_generate_skill/shopping_seven_protection.php',
                'src/lab_generate_skill/shopping_native_collection.php')
    subscription = (contract.get('family') in ('gitlab_local_artifact.atom','gitlab_local_artifact.calendar')
                    and 'required_successful_fetches' in contract.get('public_parameters',{}))
    if contract.get('domain')!='gitlab' or not (subscription or any(contract.get(k) for k in GITLAB_FLAGS)):
        return pdf_assets
    result=['scripts/gitlab_native_wiki_cache_init.rb']
    if subscription:
        result.extend('src/lab_generate_skill/'+name for name in (
            'gitlab_subscription_runtime.rb', 'gitlab_subscription_runtime.py',
            'gitlab_subscription_observation.py', 'gitlab_subscription_session.rb',
            'gitlab_subscription_session.py', 'native_failure_diagnostics.py'))
    if any(contract.get(k) for k in ('gitlab_persisted_goal','gitlab_boundary_goal','gitlab_explore_visit_goal','group_import')):
        result.append('scripts/gitlab_native_issue_cache_init.rb')
    if contract.get('gitlab_grouped_goal'):
        result.append('scripts/gitlab_issue_cache_certification.rb')
    return pdf_assets + tuple(result)


def closure(project,contracts):
    root=Path(project).resolve();names=sorted({n for c in contracts for n in required(c)});result={}
    for name in names:
        path=root/name
        if path.is_symlink()or not path.is_file():
            raise ValueError('Required frozen native asset unavailable: '+name)
        result[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def verify(project,contracts,*,frozen_manifest):
    declared=frozen_manifest
    if not isinstance(declared,dict):raise ValueError('Actual frozen runtime file manifest required')
    actual=closure(project,contracts)
    for name,digest in actual.items():
        if declared.get(name)!=digest:
            raise ValueError('Required frozen native asset is unpinned or changed: '+name)
    return {'version':'native-executable-data-preinfer-assets-v1','assets':actual,
            'ready':True,'runs_native_code':False,'actor_attempts':0,'api_calls':0}


def preflight(project,contracts,*,manifest_path):
    # The frozen worker must provide the declared file manifest from its actual
    # reviewed package. Never manufacture asset pins from the live project.
    if not any(required(c) for c in contracts):
        return verify(project,contracts,frozen_manifest={})
    if not manifest_path:
        raise ValueError('Explicit frozen native-asset manifest is required')
    manifest=Path(manifest_path)
    if not manifest.is_absolute()or manifest.is_symlink()or not manifest.is_file():
        raise ValueError('Regular absolute frozen native-asset manifest is required')
    data=json.loads(manifest.read_text())
    if not isinstance(data,dict)or not data:
        raise ValueError('Complete frozen runtime file manifest is required')
    if any(not isinstance(n,str)or Path(n).is_absolute()or '..'in Path(n).parts or not isinstance(h,str)or len(h)!=64 for n,h in data.items()):
        raise ValueError('Frozen file names and SHA256 pins must be explicit')
    result=verify(project,contracts,frozen_manifest=data)
    result['frozen_manifest_sha256']=hashlib.sha256(manifest.read_bytes()).hexdigest()
    result['declared_frozen_members']=len(data)
    from lab_generate_skill.native_pdf_reader import required as pdf_required, load as load_pdf_reader
    if any(pdf_required(c) for c in contracts):
        result['pdf_reader'] = load_pdf_reader(project)
    return result

"""Add native identity requirements without changing an original task contract."""
import copy
import hashlib
import json
from urllib.parse import urlsplit

from .gitlab_section import section_checks


def digest(contract):
    return hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def strengthens_only(candidate, original):
    revision=candidate.get('evaluator_revision',{})
    if (original.get('domain')!='gitlab' or original.get('completion',{}).get('gitlab_section')
            or revision.get('version')!='gitlab-native-section-v2'
            or revision.get('previous_contract_sha256')!=digest(original)):
        return False
    reduced=copy.deepcopy(candidate)
    reduced.pop('evaluator_revision',None);reduced.pop('native_section_evidence',None)
    spec=reduced.get('completion',{}).pop('gitlab_section',None)
    if not isinstance(spec,dict) or set(spec)!={'project_path','project_id','section_path','body_page'}:
        return False
    target=original.get('control_target_path','')
    if (spec['section_path']!=target or spec['project_path']!=target.lstrip('/').split('/-/')[0]
            or type(spec['project_id'])is not int or spec['project_id']<=0
            or not isinstance(spec['body_page'],str) or not spec['body_page'].startswith('projects:')):
        return False
    return reduced==original and bool(candidate.get('native_section_evidence'))


def bind_native_section(contract, controls):
    """Use saved positive/wrong-object captures to draft stronger checks.

    Offline agreement does not grant admission: callers must schedule two new
    native controls before an actor can use the revised contract.
    """
    from .site_navigation_rules import evaluate_navigation
    if contract.get('domain')!='gitlab' or contract.get('completion',{}).get('gitlab_section'):
        raise ValueError('Expected an original GitLab title-only section contract')
    target=contract['control_target_path'];tid=contract['task_id'];specs=[];refs=[]
    for i in range(2):
        folder=controls/f'cycle-{i}'/tid
        positive=folder/'positive.json';record=json.loads(positive.read_text());page=record['page']
        state=page['gitlab_section']
        if (page['http_status']!=200 or page['login_page'] or page['error_page']
                or urlsplit(page['url']).path.rstrip('/')!=target.rstrip('/')
                or len(state['project_ids'])!=1):raise ValueError('Invalid native section capture')
        spec={'project_path':target.lstrip('/').split('/-/')[0],'project_id':int(state['project_ids'][0]),
              'section_path':target,'body_page':state['body_page']}
        if not all(section_checks(spec,state).values()):raise ValueError('Incomplete native section identity')
        revised=copy.deepcopy(contract);revised['completion']['gitlab_section']=spec
        for name in ('positive','wrong_target','url_only'):
            file=folder/(name+'.json');page=json.loads(file.read_text())['page'];u=urlsplit(page['url'])
            status=evaluate_navigation(revised,page,site_origin=u.scheme+'://'+u.netloc)['status']
            if status!=('success'if name=='positive'else 'failure'):
                raise ValueError('Native section identity does not distinguish '+name)
            refs.append({'file':str(file.resolve()),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
        specs.append(spec)
    if specs[0]!=specs[1]:raise ValueError('Native project/section identities differ across resets')
    revised=copy.deepcopy(contract);revised['completion']['gitlab_section']=specs[0]
    revised['native_section_evidence']=refs
    revised['evaluator_revision']={'version':'gitlab-native-section-v2','previous_contract_sha256':digest(contract),
        'reason':'Add native project, page type, breadcrumb and sidebar identity; original goal, start and all existing predicates are unchanged.'}
    if not strengthens_only(revised,contract):raise ValueError('Revision changed more than native identity')
    return revised

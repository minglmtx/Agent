"""Pinned revisions over original closed Actors, never rewritten execution evidence."""
from io import BytesIO
from pathlib import PurePosixPath
import hashlib,json,tarfile


def require(value,message):
    if not value:raise ValueError(message)


def specification(owner,config,family):
    spec=owner.read(config['scope_revision'])
    require(spec['version']=='saved-reader-scope-review-v188' and spec['family']==family,'Explicit source-scoped verdict revision required')
    previous=owner.read(spec['previous_proof_config'])
    for key in ['contracts','inventory','baseline','native_review','ordinary_review','ordinary_capsule','batches']:
        require(previous[key]==config[key],'Qualified source evidence changed with verdict revision: '+key)
    require(spec['source_ids']==sorted(c['source_task_id'] for c in owner.read(config['contracts']).values()),'Verdict revision covers another source family')
    review=owner.read(spec['scope_review'])
    require(review['passed'] is True and review['production_modified'] is False and review['original_unknown_preserved'] is True,'Closed scope review required')
    package='map_saved_content_v187' if family=='save' else 'map_reader_v187'
    names=['save_judge.py','save_hooks.py'] if family=='save' else ['rss_client.py','hooks.py']
    expected={'src/lab_generate_skill/'+package+'/'+n for n in names}
    require(set(spec['qualified_component_revisions'])==expected,'Unexpected semantic scope revision member')
    for relative,row in spec['qualified_component_revisions'].items():
        require(relative.startswith('src/lab_generate_skill/') and '..' not in PurePosixPath(relative).parts,'Contained revised runtime component required')
        owner.read(dict(path=str(owner.project/relative),sha256=row['current_sha256']),json_value=False)
    return spec


def archive(owner,spec):
    index=owner.read(spec['index']);raw=owner.read(spec['archive'],json_value=False)
    require(index['archive_sha256']==spec['archive']['sha256'],'Scope archive index mismatch')
    data={};size=0
    with tarfile.open(fileobj=BytesIO(raw)) as tar:
        for member in tar:
            name=PurePosixPath(member.name);size+=member.size
            require(member.isfile() and not name.is_absolute() and '..' not in name.parts and member.name not in data and member.name in index['members'] and member.size<=128*1024**2 and size<=2*1024**3,'Unexpected scope evidence member')
            body=tar.extractfile(member).read()
            require(index['members'][member.name]==dict(bytes=len(body),sha256=hashlib.sha256(body).hexdigest()),'Scope evidence bytes changed')
            data[member.name]=body
    require(set(data)==set(index['members']),'Incomplete scope evidence archive')
    return data


def observed(data,prefix,trace,control):
    """Bind archived acknowledgements to already independently recounted messages."""
    get=lambda n:json.loads(data[prefix+n])
    messages=[m for m in trace['messages'] if m['role']=='assistant']
    require(len(messages)==trace['rounds'] and messages,'Completed first Actor required')
    issued={};bodies=[];step=0
    steps=[get(n[len(prefix):]) for n in sorted(data) if n.startswith(prefix+'step-') and n.endswith('.json')]
    for i,message in enumerate(messages):
        generation=get(f'generation-{i:03d}.json');body=json.loads(generation['messages'][-1]['content'])
        require(generation['status']=='complete' and body['goal']==control['goal'] and body['url']==steps[step]['observation']['url'],'Actual public input/source differs')
        values=issued.setdefault(str(step),[])
        if body['observation'] not in values:values.append(body['observation'])
        bodies.append(dict(step=step,body=body))
        if message['action_payload'] is not None:step+=1
    require(step+1==len(steps),'Actual browser observations incomplete')
    return issued,bodies,steps


def score_save(data,prefix,control,baseline,trace,issued,steps):
    from .map_saved_content_v187.save_judge import snapshot,evaluate
    from .map_saved_content_v187.save_snapshot import source as snapshot_source
    from .map_saved_content_v187.save_protection import check
    from .map_saved_content_v187.save_capture import witnessed
    get=lambda n:json.loads(data[prefix+n]);values={}
    kind='upload' if control['source_task_id']=='ca83744cd6665d0bf7ba' else 'diary'
    for label in ['save-before','save-after']:
        value=snapshot(get(label+'.json'));receipt=get(label+'-receipt.json');raw=data[prefix+label+'.log']
        require(receipt['read_only'] and receipt['all_public_table_triggers'] and receipt['source_sha256']==hashlib.sha256(snapshot_source().encode()).hexdigest() and receipt['raw_sha256']==hashlib.sha256(raw).hexdigest(),'Native state readout binding differs')
        require([json.loads(line) for line in raw.decode().splitlines() if line.startswith('{') and '"read_only"' in line]==[value],'Raw Rails readout differs')
        values[label]=value
    before,after=values['save-before'],values['save-after'];fb=get('save-before-files.json');fa=get('save-after-files.json')
    require(before['protection']['guard']==baseline['database'] and fb==baseline['files'] and not before['diaries'] and not before['traces'],'Original complete baseline differs')
    protection=check(kind,before['protection'],after['protection'],files_before=fb,files_after=fa);receipt=get('save-terminal.json');page=get('terminal-page.json')
    require(protection==receipt['protection'] and protection['passed'] and receipt['integrity'] is True and receipt['capture_error'] is None and page==receipt['terminal'],'Complete native save protection or terminal capture differs')
    saved=get('save-issued.json');rows=[dict(step=i,url=r['observation']['url']) for i,r in enumerate(steps)]
    require(saved==dict(observations=rows,issued=issued),'Actual issued save observations differ')
    bodies=[dict(goal=control['goal'],url=r['url'],observation='\n'.join(issued.get(str(r['step']),[]))) for r in rows]
    witness=witnessed(kind,control,bodies,get('save-index.json'));require(witness==receipt['witness'],'Actual public readback differs')
    return evaluate(kind,before,after,control,witness,page,receipt['site_origin'],trace=trace),receipt


def score_reader(data,prefix,control,baseline,trace,issued,bodies,steps):
    from .map_reader_v187.rss_client import evaluate as rss
    from .map_reader_v187.diary_read import evaluate as ny
    from .map_reader_v187.profile import declared_profile
    get=lambda n:json.loads(data[prefix+n]);before=get('reader-native-before.json');after=get('reader-native-after.json');receipt=get('reader-terminal.json');page=get('terminal-page.json')
    require(before==baseline and before['native']==after['native'] and receipt['integrity'] is True and page==receipt['terminal'],'Complete native reader state differs')
    private=dict(entries=[]);fixture=declared_profile()
    for spec in fixture['diaries']:
        rows=[r for r in before['native']['diaries'] if all(r[k]==spec[k] for k in ['title','body','latitude','longitude'])]
        require(len(rows)==1 and rows[0]['visible'] is True and rows[0]['author']==fixture['account']['display_name'],'Native diary fixture differs')
        if spec['region']=='New York City':private['entries'].append(dict(rows[0],region=spec['region']))
    require(private==get('native-diary-reference.json'),'Native diary reference differs')
    captures=[json.loads(data[n]) for n in sorted(data) if n.startswith(prefix+'reader-capture-') and n.endswith('.json')]
    require(len(captures)==len(steps),'Incomplete actual native observations')
    observations=[]
    for row in bodies:
        capture=captures[row['step']];require(capture['step']==row['step'] and capture['state']['url']==row['body']['url'],'Native capture/actual public observation differ')
        value=dict(capture['state'],step=row['step'],actual_public_text=row['body']['observation'])
        if not observations or observations[-1]!=value:observations.append(value)
    require(get('reader-issued.json')==dict(captures=captures,observations=observations),'Actual reader acknowledgement differs')
    if control['source_task_id']=='40cd6ea96d1b834eddfc':
        require(before==after,'Read-only diary task changed reader state')
        result=ny(private,observations,page,origin=receipt['site_origin'],native_unchanged=True)
    else:
        events=get('reader-events.json');responses=[dict({k:v for k,v in r.items() if k!='body_hex'},body=bytes.fromhex(r['body_hex'])) for e in events for r in e.get('responses',[])]
        matching=[r for r in observations if r['url']==page['url']];last=matching[-1] if matching else dict(ids=[],actual_public_text='')
        reopened=dict(url=page['url'],http_status=page['http_status'],error=page['error_page'],method='GET' if any(e['event']=='reader_reopened' for e in events) else None,visible_subscription_ids=last['ids'],actual_public_text=last['actual_public_text'])
        require(reopened==receipt['reopened'],'Actual RSS observation differs')
        result=rss(before['reader']['logical'],after['reader']['logical'],origin=receipt['site_origin'],responses=responses,reopened=reopened,request_events=events,trace=trace,contract=control)
    return result,receipt


def verify(owner,spec,contracts,baseline):
    original=owner.read(spec['actor_review']);scope=owner.read(spec['scope_review'])
    require(original['passed'] is True and original['archive']==spec['actor_batch']['archive'],'Wrong independent original Actor review')
    batch=spec['actor_batch'];term=owner.read(batch['termination']);complete=owner.read(batch['completed'])
    require(term['confirmed'] and term['returncode']==complete['returncode']==2 and not term['group'].get('live_members') and not term['scope']['live_scratch_references'] and not term['scope']['unreadable_same_uid_pids'],'Original unknown batch must remain closed and unmodified')
    data=archive(owner,batch);require(len(data)==original['verified_members'],'Original independent archive differs')
    worker=json.loads(data['result.json']);require(set(worker['sources'])==set(spec['source_ids']) and worker['training_admissions']==0,'Wrong source batch')
    original_rows={r['source_task_id']:r for r in original['sources']};scores={}
    for kind,control in contracts.items():
        sid=control['source_task_id'];prefix='waves/'+sid+'/'+control['task_id']+'/'
        get=lambda n:json.loads(data[prefix+n]);trace=get('trajectory.json');out=get('result.json')
        require(out==worker['sources'][sid] and out['actor_attempts']==1 and out['api_calls']==0 and out['error'] is None and trace['error'] is None and trace['task_id']==control['task_id'] and trace['task_instruction']==control['goal'],'Original first Actor/source identity differs')
        require(out['evaluation']==original_rows[sid]['judgment'],'Original Actor judgment changed')
        issued,bodies,steps=observed(data,prefix,trace,control)
        if spec['family']=='save':
            judgment,receipt=score_save(data,prefix,control,baseline,trace,issued,steps)
            expected=scope['scores']['actor-'+kind]['judgment']
        else:
            judgment,receipt=score_reader(data,prefix,control,baseline,trace,issued,bodies,steps)
            expected=scope['actor_scores'][kind]['candidate']
        require(receipt['judgment']==out['evaluation'] and judgment==expected and judgment['status'] in ('success','failure'),'Revised native verdict differs from independently scoped evidence')
        health=get('initial-page-health.json');require(health['url']==receipt['site_origin']+control['start_path']==steps[0]['observation']['url'] and health['http_status']==200 and not health['error_page'] and not health['login_page'],'Actual original starting page differs')
        events=receipt['events'];require(events[:3]==['prepare','attach','observe_initial'] and events[-4:]==['capture_terminal','close','provide_trace','score_terminal'] and events.count('record')==len(steps) and events.count('acknowledge_issued')==trace['rounds'],'Ordinary terminal-only trace delivery differs')
        scores[sid]=dict(original=out['evaluation'],revised=judgment,actor_attempts=1,source_public_input_unchanged=True)
    return scores

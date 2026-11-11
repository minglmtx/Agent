"""Read saved ordinary requests and one-account native transition; no browser."""
from pathlib import Path
import hashlib,json
from .heldout_preferences_actor_entry import public_contract,require_initial_protection,judge_transition,digest,require
from .heldout_preferences_binding import require_initial
from .heldout_preferences_protection import verify_transition
from .heldout_preferences_requests import replay_requests


def review_attempt(ready,directory,*,site_origin,model_path):
    directory=Path(directory);binding=ready['binding'];public=public_contract(binding)
    def read(name):return json.loads((directory/name).read_text())
    before,after,final=(read('protected-'+name+'.json')for name in ('before','after','final'))
    initial_guard=require_initial_protection(binding,before,ready['protected_baseline'])
    require(read('initial-protection-binding.json')==initial_guard,'Fresh initial full protection guard differs')
    verify_transition(binding,before,after);verify_transition(binding,after,final)
    require(after==final,'Final quiescent schema/protection/account seal differs')
    require(read('browser-closed.json')=={'closed':True},'Actual BrowserEnv closure not confirmed')
    for phase,snapshot in (('before',before),('after',after),('final',final)):
        from .heldout_preferences_users_schema import COLUMNS_SQL,CATALOG_SQL,validate_users_schema
        raw=read(phase+'/users-schema.json');checked=read(phase+'/users-schema-review.json')
        require(raw['columns_query']==COLUMNS_SQL and raw['catalog_query']==CATALOG_SQL
                and raw['query_error_type']is None and raw['columns']==snapshot['users_columns']
                and raw['catalog']==snapshot['users_catalog']
                and checked==dict(passed=True,checks=validate_users_schema(raw['columns'],raw['catalog'],
                    'auto_fetch_submission_titles')),'Actual complete users catalog differs')
    require(read('public-contract.json')==public,'Private fields or modified goal entered the public contract')
    task=read('public-task.json')
    from .gobrowse_runtime import BrowserTask
    require(task==BrowserTask(task_id=public['task_id'],domain='reddit',goal=public['goal'],
                      start_url=site_origin+public['start_path']).model_dump(mode='json'),'Actual BrowserTask differs')
    trace=read('trajectory-unscored.json')
    generations=[json.loads(f.read_text())for f in sorted(directory.glob('generation-*.json'))]
    steps=[json.loads(f.read_text())for f in sorted(directory.glob('step-*.json'))]
    require(steps and [r['step']for r in steps]==list(range(len(steps))),'Browser step sequence differs')
    require_initial(binding,read('initial-page.json'),before['preferences'],site_origin=site_origin)
    page=read('initial-observation-page.json')
    check=require_initial(binding,page,before['preferences'],site_origin=site_origin)
    require(read('initial-observation-binding.json')==dict(check,observation_sha256=digest(steps[0]['observation']),
            actual_observation_url=steps[0]['observation']['url'],page_url=page['url'],checked_before_first_generation=True)
            and steps[0]['observation']['url']==page['url'],'Actual first input initial guard differs')
    expected_seed=(42+int(hashlib.sha256(public['task_id'].encode()).hexdigest()[:8],16))%(2**31)
    require(trace['model']==str(model_path)and trace['seed']==expected_seed
            and trace['provenance']['actor_protocol']=='structured_observed'
            and trace['provenance']['stopping_policy']['max_steps']==20
            and trace['provenance']['start_url']==task['start_url'],'Original model/derived seed/budget differs')
    requests=replay_requests(public,trace,generations,steps)
    terminal=read('terminal-page.json')
    require(terminal['url']==steps[-1]['observation']['url'],'Terminal page differs from final browser step')
    settings=read('runtime-settings.json')
    require(settings['actor']['max_input_tokens']==16384 and settings['actor']['max_new_tokens']==512
            and settings['actor']['temperature']==0 and settings['actor']['enable_thinking']is False
            and settings['actor']['dtype']=='bfloat16'and settings['browser']['max_steps']==20
            and settings['base_seed']==42 and settings['model_path']==str(model_path)
            and settings['protocol']=='structured_observed'and settings['history_length']==6
            and settings['observation_policy']=='full-if-fits-v1'and settings['skills']==[],
            'Original ordinary Actor configuration differs')
    environment=read('native-environment.json');cache=read('terminal-thumbnail-cache.json')
    require(environment['profiler_configuration']['toolbar']is False
            and environment['profiler_configuration']['profiler_collection']is False
            and all(cache.get(k)==v for k,v in environment['original_thumbnail_cache'].items()),
            'Original native profile/cache differs')
    judgment=judge_transition(binding,terminal,before,after,site_origin=site_origin,trace_error=trace.get('error'))
    require(judgment['status']in('success','failure'),'Actual native state or protection remains unknown')
    return dict(judgment=judgment,requests=requests,actual_actor_calls=len(generations),
                initial_full_protection=True,final_protection_sealed=True,
                actual_users_schema_verified=True,private_fields_excluded=True)

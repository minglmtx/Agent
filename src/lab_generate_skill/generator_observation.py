"""Lossless actor-visible initial-page handoff; excludes evaluator/private fields."""
import json

OBSERVATION_POLICY = 'initial-ax-with-explicit-scope-v2'


def generator_observation(observation):
    tree=observation.get('axtree_txt')
    if not isinstance(tree,str) or not tree.strip():raise ValueError('Missing initial accessibility tree')
    view={'url':observation.get('url'), 'axtree_txt':tree,
          'last_action_error':observation.get('last_action_error',''),
          'record_section_state_available':'record_sections' in observation}
    if observation.get('observation_scope'):view['observation_scope']=observation['observation_scope']
    if 'record_sections' in observation:
        allowed=('bid','name','expanded','state_known','scope','control')
        view['record_sections']=[{k:r[k] for k in allowed if k in r} for r in observation['record_sections']]
    if observation.get('page_wait') is not None:view['page_wait']=observation['page_wait']
    return json.dumps(view,ensure_ascii=False)


def require_context_fit(tokenizer,messages,maximum):
    count=len(tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False))
    if count>maximum:
        raise ValueError(f'Full generator context needs {count} tokens; configured limit {maximum}. No observation was truncated; adjust context budget before generation.')
    return count

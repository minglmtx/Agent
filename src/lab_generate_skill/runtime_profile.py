"""One task-independent interface contract for website diagnostics."""
from .actor_protocol import ActorProtocol
from .adaptive_observation import select_actor_observation
from .generator_observation import generator_observation, require_context_fit
from .generator_sft import generator_messages

PROFILE = {'version':'web-unified-interface-v8-candidate','native_associated_label_click':True,'typed_action_argument_guidance':True,'native_ax_descriptions':True,'default_gitlab_reset':'offline-clone-v1','default_action_timeout_ms':5000,'observation_policy':'full-lossless-rows-if-fits-v2',
           'history_length':6,'constrain_action_names':True,'max_input_tokens':16384,
           'thought_max_characters':240,'query_max_output_tokens':4096,'collection_answers':True,'bid_generation_constraint':False,'task_specific_execution_rules':False}


def configure_actor(backend):
    backend.constrain_action_names = True
    return backend


def configure_output_budget(backend, *, query):
    """Same query/navigation budget for every site; no private values consulted."""
    if type(query) is not bool:raise ValueError('Query flag must be explicit')
    backend.settings.max_new_tokens = PROFILE['query_max_output_tokens'] if query else 512
    return backend.settings.max_new_tokens


def configure_answer_schema(backend, *, answer_fields=None, nullable_fields=()):
    """Reset public null permissions on every task, including non-query tasks."""
    from .answer_values import normalized_nullable_fields
    fields = normalized_nullable_fields(nullable_fields, answer_fields=answer_fields or ())
    backend._action_nullable_answer_fields = fields
    return fields


def actor_protocol(answer_fields=None, *, nullable_answer_fields=()):
    return ActorProtocol('structured_observed', history_length=PROFILE['history_length'],
                         answer_fields=answer_fields, nullable_answer_fields=nullable_answer_fields, observation_policy=PROFILE['observation_policy'])


def generator_request(goal, obs, refs, tokenizer, maximum=16384):
    def build(view):
        return generator_messages(goal,generator_observation(view),refs)
    def count(messages):
        return len(tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False))
    selected=select_actor_observation(obs,build,count,maximum,compact_rows=True)
    messages=build(selected)
    # A viewport that is itself too large is explicitly blocked, never left-truncated.
    tokens=require_context_fit(tokenizer,messages,maximum)
    return generator_observation(selected),messages,tokens,selected['observation_mode']

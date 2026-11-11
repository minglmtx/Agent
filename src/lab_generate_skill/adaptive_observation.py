"""Select current-page AX using actual complete-request token counts."""
from .browser_prompt_contract import VIEWPORT_GUIDANCE, FULL_AX_GUIDANCE
from .observation_budget import ObservationBudgetError


def select_actor_observation(obs, build_messages, count_tokens, maximum=16384, *, compact_rows=False):
    full_tree=obs.get('axtree_full_txt')
    if not isinstance(full_tree,str) or not full_tree.strip():
        raise ObservationBudgetError('Hybrid observation requires the actual full current-page AX')
    full={**obs, 'axtree_txt':full_tree, 'observation_scope':FULL_AX_GUIDANCE,
          'observation_mode':'full', 'observation_policy':'full-if-fits-v1'}
    if count_tokens(build_messages(full))<=maximum:
        return full
    if compact_rows:
        from .lossless_ax_rows import compact,GUIDANCE
        encoded=compact(full_tree)
        if encoded!=full_tree:
            packed={**full,'axtree_txt':encoded,'observation_scope':FULL_AX_GUIDANCE+'\n'+GUIDANCE,
                    'observation_policy':'full-lossless-rows-if-fits-v2'}
            if count_tokens(build_messages(packed))<=maximum:return packed
    # No data truncation: fallback retains the actual viewport.
    return {**obs, 'observation_scope':VIEWPORT_GUIDANCE,
            'observation_mode':'viewport', 'observation_policy':'full-if-fits-v1'}

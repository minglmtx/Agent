"""Current ordinary hooks for exactly reviewed initial-view link contracts."""
from copy import deepcopy
from . import map_initial_view_link_runtime as runtime
from .initial_link_review_catalog import VERSION
from .source_revision_binding import require_source_binding


class FrozenInitialLinkActorAdapter:
    FEEDBACK_VERSIONS=(runtime.rule.VERSION,)
    AUTHORIZED_TARGET_WRITES=False

    def __init__(self,*,resolve_proof):self.resolve=resolve_proof
    def enabled(self,c):return c.get('domain')=='map' and 'reviewed_initial_link'in c
    def canonical(self,c):
        if not self.enabled(c)or c['reviewed_initial_link']!={'version':VERSION}:
            raise ValueError('Explicit reviewed initial-link source required')
        return deepcopy({k:v for k,v in c.items()if k!='admission_result'})
    def verified(self,c,descriptor):
        candidate=self.canonical(c);source=self.resolve(candidate['source_task_id'],descriptor)
        if source['candidate']!=candidate or source['admission'].get('passed')is not True:
            raise ValueError('Initial-link source differs from native proof')
        return source
    def require_admission(self,c,descriptor):return deepcopy(self.verified(c,descriptor)['admission'])
    def require_original_binding(self,c,original,inventory):
        return require_source_binding(self.canonical(c),original,inventory,domain='map')
    def NativeReadHooks(self,c,descriptor,directory):
        source=self.verified(c,descriptor)
        return runtime._InitialViewHooks(source['original'],source['baseline'],directory,source['reference'])
    def public_goal(self,c):return self.canonical(c)['goal']
    def fields(self,c):self.canonical(c);return ['share_link']
    def feedback(self,judgment):
        if judgment.get('version')not in self.FEEDBACK_VERSIONS:raise ValueError('Unknown map-link feedback')
        return runtime.feedback(judgment)

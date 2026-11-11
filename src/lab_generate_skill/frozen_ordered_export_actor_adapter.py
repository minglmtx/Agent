"""Bind the shared ordinary runner to reviewed ordered export semantics."""
from copy import deepcopy
from .map_ordered_export import VERSION,validate,fingerprint,feedback
from .map_ordered_export_observation import OrderedExportHooks
from .source_revision_binding import require_source_binding

class FrozenOrderedExportActorAdapter:
    FEEDBACK_VERSIONS=(VERSION,)
    AUTHORIZED_TARGET_WRITES=False
    def __init__(self,*,resolve_proof):
        if not callable(resolve_proof):raise ValueError('Frozen composition resolver required')
        self.resolve=resolve_proof
    def enabled(self,c):return c.get('domain')=='map' and 'ordered_export'in c
    def canonical(self,c):
        if not self.enabled(c):raise ValueError('Ordered export task required')
        value=deepcopy({k:v for k,v in c.items()if k!='admission_result'});validate(value);return value
    def verified(self,c,descriptor):
        c=self.canonical(c);source=self.resolve(c['source_task_id'],descriptor);a=source['admission']
        if (source['candidate']!=c or a.get('version')!='native-ordered-export-admission-v1'
            or a.get('passed')is not True or a.get('full_ordered_controls_verified')is not True
            or a.get('reset_verified')is not True or a.get('source_task_id')!=c['source_task_id']
            or a.get('composition_fingerprint')!=fingerprint(c)
            or a.get('baseline')!=source['baseline'] or a.get('environment_binding')!=source['environment_binding']):
            raise ValueError('Exact task, composition and reset proof required')
        return source
    def require_admission(self,c,descriptor):return deepcopy(self.verified(c,descriptor)['admission'])
    def require_original_binding(self,c,original,inventory):return require_source_binding(self.canonical(c),original,inventory,domain='map')
    def NativeReadHooks(self,c,descriptor,directory):
        source=self.verified(c,descriptor)
        return OrderedExportHooks(self.canonical(c),directory,environment_binding=source['environment_binding'],baseline=source['baseline'])
    def public_goal(self,c):return self.canonical(c)['goal']
    def fields(self,c):self.canonical(c);return []
    def feedback(self,judgment):return feedback(judgment)

"""GPS overlay adapter: passive state observation, final-only scoring."""
from copy import deepcopy
from .map_gps_overlay_observation import GPSObservationHooks
from .map_gps_overlay_terminal import VERSION
from .map_provider_contract import validate_resource_family
from .source_revision_binding import require_source_binding

class FrozenGPSActorAdapter:
    FEEDBACK_VERSIONS=(VERSION,)
    AUTHORIZED_TARGET_WRITES=False
    def __init__(self,*,resolve_proof):
        if not callable(resolve_proof):raise ValueError('Verified GPS proof resolver required')
        self.resolve=resolve_proof
    def enabled(self,c):
        return c.get('domain')=='map'and c.get('candidate_completion',{}).get('family')=='gps_overlay'
    def canonical(self,c):
        if not self.enabled(c):raise ValueError('GPS contract required')
        value=deepcopy({k:v for k,v in c.items()if k!='admission_result'})
        validate_resource_family(value['candidate_completion']);return value
    def verified(self,c,descriptor):
        c=self.canonical(c);s=self.resolve(c['source_task_id'],descriptor);a=s['admission']
        if (s['candidate']!=c or a.get('version')!='native-gps-normal-admission-v1'
                or a.get('source_task_id')!=c['source_task_id']
                or a.get('baseline')!=s['baseline']or not s['baseline']
                or a.get('environment_binding')!=s['environment_binding']
                or any(a.get(k)is not True for k in ('passed','ordinary_lifecycle_verified',
                    'reset_verified','genuine_visible_tracks_verified','missing_response_rejected'))):
            raise ValueError('Exact GPS task, state, and terminal controls required')
        return s
    def require_admission(self,c,descriptor):return deepcopy(self.verified(c,descriptor)['admission'])
    def require_original_binding(self,c,original,inventory):
        return require_source_binding(self.canonical(c),original,inventory,domain='map')
    def NativeReadHooks(self,c,descriptor,directory):
        s=self.verified(c,descriptor)
        return GPSObservationHooks(self.canonical(c),directory,environment_binding=s['environment_binding'],baseline=s['baseline'])
    def public_goal(self,c):return self.canonical(c)['goal']
    def fields(self,c):self.canonical(c);return []
    def feedback(self,judgment):
        if judgment.get('version')!=VERSION:raise ValueError('GPS final-only judgment required')
        return dict(status=judgment['status'],reward=judgment['reward'],
            checks=[dict(condition=k,passed=v)for k,v in judgment.get('checks',{}).items()if type(v)is bool],
            private_reference_values_provided=False,action_sequence_provided=False)

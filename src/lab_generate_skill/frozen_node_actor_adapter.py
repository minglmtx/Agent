"""Native node edits use the ordinary browser actor and terminal readback.

Only an independently reviewed resolver may supply admission. This adapter
neither constructs control evidence nor grants training publication.
"""
from copy import deepcopy
from .frozen_route_actor_adapter import FrozenRouteActorAdapter
from .map_node_episode import NodeEpisodeHooks
from .map_node_task import environment_key


def initial_signature(initial):
    return dict(environment=initial['environment'],fixture_ids=initial['fixture_ids'],
        owner_id=initial['owner_id'],max_node_id=initial['snapshot']['max_node_id'],
        max_changeset_id=initial['snapshot']['max_changeset_id'],records=[dict(
            node_id=r['node_id'],tags=r['record']['tags'],current={k:r['record']['current'][k]
            for k in ('id','version','changeset_id','latitude','longitude','visible')},
            owner=r['record']['changeset_owner'])for r in initial['snapshot']['records']])


class BoundNodeHooks(NodeEpisodeHooks):
    def __init__(self,candidate,directory,*,profile,expected_initial):
        super().__init__(candidate,directory,profile=profile)
        self.expected_initial=deepcopy(expected_initial)

    def prepare(self,site,username):
        super().prepare(site,username)
        if initial_signature(self.initialization)!=self.expected_initial:
            raise ValueError('Native node initial state differs from reviewed cold baseline')


class FrozenNodeActorAdapter(FrozenRouteActorAdapter):
    AUTHORIZED_TARGET_WRITES=True
    FEEDBACK_VERSIONS=('native-map-node-task-v1',)

    def feedback(self, judgment):
        # Node results must not inherit the route-only formatter from a frozen
        # base runtime. Expose Boolean completion checks, never saved objects
        # or private reference values from the native node readback.
        if judgment.get('version') not in self.FEEDBACK_VERSIONS:
            raise ValueError('Native node terminal judgment required')
        return dict(status=judgment['status'], reward=judgment['reward'],
            checks=[dict(condition=k, passed=v)
                    for k, v in judgment['checks'].items() if type(v) is bool],
            private_reference_values_provided=False, action_sequence_provided=False)

    def enabled(self,c):
        return c.get('domain')=='map'and c.get('candidate_completion',{}).get('family')=='persisted_map_node'

    def verified(self,c,descriptor):
        candidate=self.canonical(c);source=self.resolve(candidate['source_task_id'],descriptor)
        admission=source['admission']
        required=('passed','ordinary_lifecycle_verified','source_start_verified',
                  'persisted_controls_verified','native_write_audit_verified','cold_reset_verified')
        if (source['candidate']!=candidate or admission.get('version')!='native-node-task-admission-v1'
                or admission.get('source_task_id')!=candidate['source_task_id']
                or any(admission.get(k)is not True for k in required)
                or not source.get('initial_signature')):
            raise ValueError('Exact node source, native saved-state controls and cold reset required')
        key=environment_key(candidate,source['profile'])
        if source['initial_signature'].get('environment')!=key:
            raise ValueError('Reviewed node environment does not match declared initialization')
        return source

    def NativeReadHooks(self,c,descriptor,directory):
        source=self.verified(c,descriptor)
        return BoundNodeHooks(self.canonical(c),directory,profile=source['profile'],
                              expected_initial=source['initial_signature'])

    def profile_for_contracts(self,contracts):
        rows=list(contracts)
        if not rows or not all(self.enabled(c)for c in rows):
            raise ValueError('Dedicated node editing manifest required')
        # Existing manifest planner selects the declared community service.
        return {}

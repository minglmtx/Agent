"""New route scope authority from retained controls plus exact new public inputs."""
from copy import deepcopy
from lab_generate_skill.map_route_normal_capture import fingerprint
from map_scope_v183.route_scope import ScopeRouteAdapter,ScopeRouteHooks,validate_mapping,require

class AdmittedScopeRouteAdapter(ScopeRouteAdapter):
    def verified(self,candidate,descriptor):
        c=self.canonical(candidate);source=self.resolve(c['source_task_id'],descriptor)
        require(source['candidate']==c,'Exact revised public contract required')
        mapping=validate_mapping(source['historical_candidate'],c)
        require(source['scope_binding']==mapping,'Original source scope mapping changed')
        proof=source['current_input_replay'];admission=source['admission'];original=source['historical_admission']
        require(proof.get('passed')is True and proof['source_task_id']==c['source_task_id']and proof['candidate_sha256']==fingerprint(c)
            and proof['raw_messages_exact_under_current_runtime']is True and proof['independent_native_input_reader_passed']is True,
            'Actual new native input must replay exactly under current code')
        require(original['version']=='native-route-normal-admission-v1'and original['source_task_id']==c['source_task_id']
            and all(original.get(k)is True for k in ('passed','two_cold_environment_verified','ordinary_lifecycle_verified','all_route_alternatives_verified','native_output_controls_verified','reset_verified')),
            'Complete retained native route controls required')
        require(original['baseline']==source['baseline']and source['baseline']and source['references'],'Exact native reference baseline required')
        require(admission==dict(version='native-website-offered-route-admission-v185',source_task_id=c['source_task_id'],candidate_sha256=fingerprint(c),
            baseline=source['baseline'],passed=True,retained_native_controls_verified=True,new_actual_input_verified=True,first_actor_verified=False,training_admitted=False),
            'Explicit revised-scope admission required')
        return source

    def NativeReadHooks(self,candidate,descriptor,directory):
        source=self.verified(candidate,descriptor)
        return ScopeRouteHooks(self.canonical(candidate),directory,baseline=source['baseline'],references=source['references'],frontend_source=source['scope_frontend']['path'])

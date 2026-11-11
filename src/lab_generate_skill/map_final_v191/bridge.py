"""Current registry delegates to the same qualified native implementations."""
from lab_generate_skill.remaining_route_actor_adapter import RemainingRouteAdapter
from lab_generate_skill.map_offered_route_v189.adapter import AdmittedScopeRouteAdapter
from lab_generate_skill.map_edit_v190.adapter import Adapter as QualifiedEdit
from lab_generate_skill.map_scope_v190.adapter import Bridge

ROUTES=frozenset(('741896107a1f2301d290','a1078549f94ed0af0411',
                  'aecc474f08b43bd57981','21482bd3a34a1ca47051'))

class RouteAdapter:
 AUTHORIZED_TARGET_WRITES=False
 FEEDBACK_VERSIONS=tuple(sorted(set(RemainingRouteAdapter.FEEDBACK_VERSIONS)|
                                set(AdmittedScopeRouteAdapter.FEEDBACK_VERSIONS)))
 def __init__(self,*,resolve_proof):
  self.ordinary=RemainingRouteAdapter(resolve_proof=resolve_proof)
  self.offered=AdmittedScopeRouteAdapter(resolve_proof=resolve_proof)
 def enabled(self,c):
  return c.get('source_task_id')in ROUTES and c.get('domain')=='map'
 def delegate(self,c):
  if not self.enabled(c):raise ValueError('Exact reviewed route source required')
  return self.offered if c['source_task_id']=='741896107a1f2301d290'else self.ordinary
 def canonical(self,c):return self.delegate(c).canonical(c)
 def require_admission(self,c,p):return self.delegate(c).require_admission(c,p)
 def require_original_binding(self,c,o,i):return self.delegate(c).require_original_binding(c,o,i)
 def NativeReadHooks(self,c,p,d):return self.delegate(c).NativeReadHooks(c,p,d)
 def public_goal(self,c):return self.delegate(c).public_goal(c)
 def fields(self,c):return self.delegate(c).fields(c)
 feedback=RemainingRouteAdapter.feedback

class EditAdapter(Bridge):
 AUTHORIZED_TARGET_WRITES=True
 FEEDBACK_VERSIONS=QualifiedEdit.FEEDBACK_VERSIONS
 def enabled(self,c):
  return c.get('source_task_id')=='35984f23d32598fe54dd'and c.get('domain')=='map'and c.get('validation_scope')==self.FEEDBACK_VERSIONS[0]
 feedback=QualifiedEdit.feedback
 def profile_for_contracts(self,rows):
  if len(rows)!=1:raise ValueError('Dedicated native edit source required')
  return self.source(rows[0])['adapter'].profile_for_contracts(rows)

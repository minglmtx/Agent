"""Optional typed-query lifecycle hooks; strict dispatch and private evidence.

This helper can be wired into the existing runner after shared imports are
released. It never changes an action, observation, initial URL or source
reference, and cannot upgrade a capability-only proof into admission.
"""
import copy
from pathlib import Path
from . import map_typed_runtime as runtime


def enabled(contract):
    query=contract.get('query')
    return isinstance(query,dict) and query.get('family')==runtime.FAMILY


class TypedQueryHooks:
    def __init__(self,contract,proof,directory):
        if not enabled(contract):
            raise ValueError('The exact typed Map query family is required')
        self.contract=copy.deepcopy(contract)
        self.proof=copy.deepcopy(proof)
        self.directory=Path(directory)
        self.cycles=runtime.task_cycle_views(self.contract,self.proof)
        self.timeline=runtime.ShareTimeline(self.contract,self.directory)
        self.initial_verified=False

    @property
    def expected_reference(self):
        return copy.deepcopy(self.cycles[0]['initial_reference'])

    @property
    def expected_fingerprint(self):
        return self.cycles[0]['initial_fingerprint']

    def prepare(self,site,*,browser=None):
        result=runtime.prepare_site(site,self.contract,self.directory,browser=browser)
        if result!=self.expected_reference:
            raise RuntimeError('Typed native reference differs from both approved cycles')
        return result

    def verify_baseline(self,reference,fingerprint):
        if reference!=self.expected_reference or fingerprint!=self.expected_fingerprint:
            raise RuntimeError('Typed source reference or native baseline differs from admission')

    def observe_initial(self,page):
        result=runtime.observe_initial(page,self.contract,self.proof,self.directory)
        self.initial_verified=True
        return result

    def record(self,page,*,event='issued_observation'):
        if not self.initial_verified:
            raise RuntimeError('Verify the original initial state before issuing typed observations')
        # This is evaluator-only; the return value must never be appended to AX.
        return self.timeline.record(page,event=event)

    def observations(self):
        return runtime.load_share_timeline(self.contract,self.directory)

    def public_goal(self):
        return runtime.public_goal(self.contract)


def goal(contract,*,generic):
    return runtime.public_goal(contract) if enabled(contract) else generic(contract)


def reference(site,contract,*,generic):
    return runtime.reference(site,contract) if enabled(contract) else generic(site,contract)


def admission(contract,proof,*,generic):
    return runtime.require_admission(contract,proof) if enabled(contract) else generic(contract,proof)


def evaluate(contract,page,answer,initial,final,*,site_origin,generic,observations=None,runtime_error=None):
    if enabled(contract):
        return runtime.evaluate(contract,page,answer,initial,final,site_origin=site_origin,
                                observations=observations,runtime_error=runtime_error)
    # Preserve the old evaluator signature and arguments for every other family.
    return generic(contract,page,answer,initial,final,site_origin=site_origin,runtime_error=runtime_error)


def feedback(contract,judgment,*,generic):
    return runtime.feedback(judgment) if enabled(contract) else generic(judgment)

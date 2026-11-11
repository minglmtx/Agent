"""Normal-runner adapters for explicitly delivered, reviewed Reddit families.

The frozen worker bootstrap installs these after verifying its package. Nothing
is imported from a path or module named by a task. Original family implementations
and their provenance-sensitive admission gates stay unchanged. CPU-only control
constructors are deliberately unavailable here.
"""
from dataclasses import dataclass
import importlib
import json

from .source_revision_binding import require_source_binding


@dataclass(frozen=True, eq=False)
class FamilyAdapter:
    module: object
    constructor_name: str
    AUTHORIZED_TARGET_WRITES: bool = False
    include_public_parameters: bool = False

    @property
    def FEEDBACK_VERSIONS(self):
        return (self.module.VERSION,)

    def enabled(self, contract):
        return self.module.enabled(contract)

    def require_admission(self, contract, proof):
        return self.module.require_admission(contract, proof)

    def require_original_binding(self, contract, original, inventory):
        method = getattr(self.module, 'require_original_binding', None)
        if method:
            return method(contract, original, inventory)
        return require_source_binding(contract, original, inventory, domain='reddit')

    def NativeReadHooks(self, contract, proof, directory):
        from .reddit_terminal_failure import wrap
        hooks = getattr(self.module, self.constructor_name)(contract, proof, directory)
        return wrap(hooks, self.module)

    def fields(self, contract):
        method = getattr(self.module, 'fields', None)
        self.enabled(contract)
        return method(contract) if method else []

    def public_goal(self, contract):
        goal = self.module.public_goal(contract)
        if self.include_public_parameters:
            goal += '\nPublic task parameters: ' + json.dumps(
                contract['public_parameters'], ensure_ascii=False, sort_keys=True)
        return goal

    def feedback(self, judgment):
        # Same public feedback contract as the reviewed candidate factory.
        # Do not copy private expected values or a scripted action sequence.
        return {'status': judgment['status'], 'reward': judgment['reward'],
                'checks': {key: value for key, value in judgment.get('checks', {}).items()
                           if type(value) is bool},
                'private_reference_values_provided': False,
                'action_sequence_provided': False}

    def upload_files(self, contract, hooks):
        method = getattr(self.module, 'upload_files', None)
        return method(contract) if method else []


# Family-level registrations, never source IDs or actor action corrections.
# FinalReadingHooks already has a native dispatcher slot; do not register twice.
FAMILIES = (
    ('lab_generate_skill.reddit_parented_reply_runtime', 'ParentedReplyHooks', True, False),
    ('lab_generate_skill.reddit_reading_bridge_runtime', 'ReadingBridgeHooks', False, False),
    ('lab_generate_skill.reddit_candidate_search_runtime', 'SearchCompletionHooks', False, True),
    ('reddit_local_post_candidate', 'NativeReadHooks', True, False),
    ('reddit_local_read_hooks', 'NativeReadHooks', False, False),
    ('reddit_rss_subscription_hooks', 'NativeReadHooks', False, False),
    ('reddit_media_protocol', 'MediaHooks', True, False),
)


def install(dispatch, *, runner):
    """Call once in a fresh worker after frozen package/import validation."""
    adapters = [(name, FamilyAdapter(importlib.import_module(name), ctor, writes, public))
                for name, ctor, writes, public in FAMILIES]
    # Check constructor availability before mutating dispatcher registration.
    for _, adapter in adapters:
        if not callable(getattr(adapter.module, adapter.constructor_name, None)):
            raise ValueError('Reviewed ordinary constructor is unavailable')
    for name, adapter in adapters:
        dispatch.register_protocol(name, adapter)
    # The original control factory renders public task parameters for reading
    # families too. Reuse its public-only renderer so Task.setup and the online
    # caller receive precisely the same declared goal, including an empty {}.
    # This does not replace any evaluator or ordinary hook constructor.
    factory=importlib.import_module('lab_generate_skill.reddit_candidate_factory')
    factory.install_normal_goal_renderer(runner)
    return dict(adapters)

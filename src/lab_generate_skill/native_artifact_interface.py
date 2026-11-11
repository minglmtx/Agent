"""Optional shared BrowserGym artifact interface candidate.

The public tools do not contain expected answers or source-specific strategies.
This module never bypasses source admission. Callers must first run their real
complete native proof callback. No default callback or success stub is provided.
"""
from copy import deepcopy
from contextlib import contextmanager
import json
from pathlib import Path

from lab_generate_skill.local_artifact_actions import TOOL_SCHEMAS
from lab_generate_skill.prompting import parse_json_object
from .native_artifact_client import LocalArtifactActions, artifact_call, write

INTERFACE_VERSION = 'native-artifact-public-browser-interface-candidate-v1'
DESCRIPTION = '''Optional local artifact client operations:
clone_repository(url): clone a native repository URL currently exposed in the
page into this attempt's isolated local worktree, preserving all branches/tags.
subscribe_feed(url,kind): subscribe this attempt's local client to an observed
native feed. kind is atom or calendar. This is a declared local-client extension.
refresh_subscription(subscription_id): refresh a subscription made in this attempt.
list_local_artifacts(): inspect this attempt's actual local artifact records.
These functions perform client operations; they do not declare task success.
Use only the public URLs shown in the current observation. A repository link,
calendar link, download, or a copied URL is not a clone or active subscription.
'''


class ArtifactProtocol:
    """Delegate existing browser protocol; add only the declared client calls."""
    def __init__(self, browser_protocol):
        self.browser_protocol = browser_protocol; self.name = browser_protocol.name

    def __getattr__(self, name):
        return getattr(self.browser_protocol, name)

    def prepare_observation(self, goal, obs, history, *, token_counter=None,
                            action_description=None, skills=None):
        if self.browser_protocol.observation_policy == 'viewport-v1': return obs
        if token_counter is None: raise ValueError('Actual tokenizer counter required')
        from lab_generate_skill.adaptive_observation import select_actor_observation
        return select_actor_observation(obs, lambda output:self.messages(goal,output,history,
            action_description=action_description,skills=skills),token_counter)

    def messages(self, *args, **kwargs):
        messages = self.browser_protocol.messages(*args, **kwargs)
        messages = deepcopy(messages)
        messages[0]['content'] += '\n' + DESCRIPTION
        return messages

    def parse(self, text, obs):
        value = parse_json_object(text)
        if self.name == 'baseline':
            action = value.get('action')
            if isinstance(action, str):
                call = artifact_call(action)
                if call is not None: return action.strip(), str(value.get('thought') or '')
        elif value.get('action') in TOOL_SCHEMAS:
            args = value.get('args')
            if not isinstance(args, list): raise ValueError('Artifact args must be a JSON array')
            action = value['action'] + '(' + ', '.join(repr(v) for v in args) + ')'
            artifact_call(action)
            return action, str(value.get('thought') or '')
        return self.browser_protocol.parse(text, obs)


def _session_extension(base_factory, *, artifact_root, site_origin, source_task_id,
                       hooks, current_account_auth):
    root = Path(artifact_root)
    if root.exists(): raise ValueError('Each attempt requires a fresh private artifact root')
    class Session(base_factory):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.artifact_actions = None
            self.action_description += '\n' + DESCRIPTION
            self.artifact_action_receipts = []
        def _public(self, obs):
            try: public = self.artifact_actions.observe_page(self.env.page)
            except ValueError:
                # Error/foreign documents have no usable native artifact URLs.
                # They remain ordinary observations and terminal failures.
                self.artifact_actions.observe_native_urls(); public = {'clones': [], 'feeds': []}
            artifacts = self.artifact_actions.list_local_artifacts()
            addition = '\n\n# Current native artifact URLs and local artifacts\n' + json.dumps(
                {'native_urls': public, 'local_artifacts': artifacts}, ensure_ascii=False)
            output = dict(obs); output['axtree_txt'] = obs.get('axtree_txt', '') + addition
            if 'axtree_full_txt' in obs: output['axtree_full_txt'] += addition
            return output
        def reset(self, seed):
            obs, info = super().reset(seed)
            self.artifact_actions = LocalArtifactActions(root, site_origin,
                self.env.page.context.request, current_account_auth=current_account_auth)
            hooks.bind_client(self.artifact_actions)
            return self._public(obs), info
        def step(self, action):
            parsed = artifact_call(action)
            if parsed is None:
                result = super().step(action); return (self._public(result[0]), *result[1:])
            error = ''
            try:
                self.artifact_actions.observe_page(self.env.page)
                value = self.artifact_actions.dispatch(*parsed)
                receipt = {'operation_result': value}
            except ValueError as exc:
                error = 'Local artifact action rejected: ' + str(exc)[:500]
                receipt = {'operation_error': {'type': 'ValueError', 'reason': error}}
            self.artifact_action_receipts.append({'action': action, **receipt,
                'source_task_id': source_task_id, 'task_success_not_evaluated': True})
            write(root / 'actual-client-actions.json', self.artifact_action_receipts)
            result = super().step('noop()')
            obs = self._public(result[0]); obs['last_action_error'] = error
            # Preserve the actual tool call in ordinary per-step records. The
            # browser noop is only the observation refresh, not actor policy.
            step = root.parent / ('step-' + str(self.index - 1).zfill(3) + '.json')
            if not step.is_file() or step.is_symlink():
                raise ValueError('Actual ordinary artifact observation record missing')
            row = json.loads(step.read_text())
            if row.get('action') != 'noop()':
                raise ValueError('Ordinary artifact observation refresh record differs')
            row.update(action=action, observation=obs,
                browser_observation_refresh_action='noop()', actual_local_client_operation=True)
            write(step, row)
            return (obs, *result[1:])
    return Session


def configure_protocol(backend, browser_protocol, *, enabled):
    """Called by a trusted admitted runtime; always clear prior task capability."""
    if type(enabled) is not bool:
        raise ValueError('Explicit admitted artifact capability required')
    backend._native_artifact_action_names = tuple(sorted(TOOL_SCHEMAS)) if enabled else ()
    return ArtifactProtocol(browser_protocol) if enabled else browser_protocol


@contextmanager
def actor_bridge(runner, adapter):
    """Pair admitted session tools with the current decoder, without replacing it.

    The ordinary runner constructs its session factory before its protocol.
    A matching family name alone never enables tools: the native adapter must
    already have checked and bound that exact contract to a prepared attempt.
    """
    from .frozen_native_artifact_adapter import FrozenNativeArtifactAdapter, session_bridge
    if not isinstance(adapter, FrozenNativeArtifactAdapter):
        raise ValueError('Trusted admitted native artifact adapter required')
    original = runner.task_actor_protocol
    if getattr(original, '_admitted_artifact_protocol_bridge', False):
        raise ValueError('An artifact protocol bridge is already installed')
    backends = {}

    def protocol(backend, contract, **kwargs):
        backends[id(backend)] = backend
        # Clear even when the next task or protocol construction is rejected.
        backend._native_artifact_action_names = ()
        enabled = adapter.enabled(contract)
        if enabled and not adapter.has_bound_session(contract):
            raise ValueError('Artifact protocol requires an actually bound admitted session')
        browser = original(backend, contract, **kwargs)
        return configure_protocol(backend, browser, enabled=enabled)

    protocol._admitted_artifact_protocol_bridge = True
    with session_bridge(runner, adapter):
        runner.task_actor_protocol = protocol
        try:
            yield
        finally:
            for backend in backends.values():
                backend._native_artifact_action_names = ()
            if runner.task_actor_protocol is not protocol:
                raise ValueError('Another owner replaced the ordinary actor protocol')
            runner.task_actor_protocol = original


def bind_session_factory(base_factory, *, artifact_root, site_origin,
                         candidate_root, plan, driver_module, case, cycles, directories,
                         hooks, current_account_auth):
    from driver_registry import verify_entry, validate_plan
    validate_plan(plan, 'gitlab')
    sources = [row for row in plan['cases'] if row['source_task_id'] == case['source_task_id']]
    if len(sources) != 1: raise ValueError('Exact reviewed source required')
    original = sources[0]
    for field in ('driver_key','original_goal','recorded_start_urls','source_trace_ids'):
        if case.get(field) != original.get(field): raise ValueError('Original source binding differs')
    key = case['driver_key']; path = verify_entry(candidate_root, key, plan['driver_entries'][key])
    if not getattr(driver_module, '__file__', None) or Path(driver_module.__file__).resolve() != path.resolve():
        raise ValueError('Actual frozen source driver callback required')
    proof = driver_module.require_two_cold(case, cycles, directories)
    if (proof.get('passed') is not True or proof.get('source_task_id') != case['source_task_id']
        or proof.get('fresh_cycles') != 2 or proof.get('contract') != case):
        raise ValueError('Complete original source native proof failed')
    return _session_extension(base_factory, artifact_root=artifact_root,
        site_origin=site_origin, source_task_id=case['source_task_id'], hooks=hooks,
        current_account_auth=current_account_auth)


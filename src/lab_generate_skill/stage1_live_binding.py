"""Exact live-start comparison from the reviewed GitLab continuation."""
import json
from urllib.parse import urlsplit
from copy import deepcopy
from pathlib import Path

from .generator_sft import file_hash
from .stage1_local import read_pinned_json


def validate_qualified_capture(qualification, current):
    """Compare the actual no-inference messages with the qualified capture.

    Only isolated local origins and measured wait duration may differ. Every
    business value, system instruction, tab title, route, observation and
    action/history field remains exact. No comparison metadata enters prompts.
    """
    reference = qualification['actual_captured_contexts'][0]
    previous = read_pinned_json(reference)
    observation = qualification['initial_observation']
    if file_hash(observation['path']) != observation['sha256']:
        raise ValueError('Qualified initial observation changed')
    expected_text = Path(observation['path']).read_text()
    changes = []

    def canonical(value, label):
        if (value.get('status') != 'context_prepared' or value.get('sent_to_model') is not False
                or value.get('model_calls') != 0 or value.get('actor_actions') != 0):
            raise ValueError('Qualified binding requires no-inference context capture')
        messages = deepcopy(value['messages'])
        users = [m for m in messages if m['role'] == 'user']
        if len(users) != 1:
            raise ValueError('Expected exactly one initial public user context')
        body = json.loads(users[0]['content'])
        if body.get('observation') != expected_text:
            raise ValueError('Current initial observation differs from qualified evidence')

        def local_route(raw):
            url = urlsplit(raw)
            if (url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost')
                    or not url.port or url.username or url.password):
                raise ValueError('Initial comparison permits only isolated local origins')
            changes.append(dict(capture=label, local_origin=url.netloc))
            return (url.path, url.query, url.fragment)

        body['url'] = local_route(body['url'])
        for tab in body.get('open_tabs', []):
            tab['url'] = local_route(tab['url'])
        wait = body.get('page_wait')
        if isinstance(wait, dict) and 'seconds' in wait:
            elapsed = wait.pop('seconds')
            if type(elapsed) not in (int, float) or not 0 <= elapsed < 60:
                raise ValueError('Invalid measured wait duration')
            changes.append(dict(capture=label, measured_wait_seconds=elapsed))
        users[0]['content'] = body
        return messages

    if canonical(previous, 'qualified') != canonical(current, 'current'):
        raise ValueError('Current public initial messages differ from qualified evidence')
    return dict(passed=True, qualified_context=reference, qualified_observation=observation,
                exact_business_values=True, checked_before_generator_or_actor=True,
                permitted_private_comparison_differences=changes)

def validate_live_start(old, current):
    for key in ('task', 'initial_observation', 'website_snapshot_id', 'observation_policy', 'model_calls'):
        if old[key] != current[key]:
            raise ValueError('Live resume context differs: ' + key)
    before = json.loads(old['generator_observation'])
    after = json.loads(current['generator_observation'])
    a, b = urlsplit(before['url']), urlsplit(after['url'])
    for url in (a, b):
        if (url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost')
                or not url.port or url.username or url.password):
            raise ValueError('Only isolated local origins can be rebound')
    if (a.path, a.query, a.fragment) != (b.path, b.query, b.fragment):
        raise ValueError('Live resume start route changed')
    changes = dict(old_url=before.pop('url'), current_url=after.pop('url'))
    # The wait's measured elapsed seconds are instrumentation, never page data.
    # Keep policy, status, signals and all other wait fields equal.
    for label, obj in [('old', before), ('current', after)]:
        wait = obj.get('page_wait')
        if isinstance(wait, dict) and 'seconds' in wait:
            elapsed = wait.pop('seconds')
            if type(elapsed) not in (int, float) or not 0 <= elapsed < 60:
                raise ValueError('Invalid page wait instrumentation')
            changes[label + '_wait_seconds'] = elapsed
    if before != after:
        raise ValueError('Live resume public state changed beyond local origin/wait timing')
    return dict(passed=True, ax_exactly_equal=True, all_business_values_preserved=True,
                original_cached_model_messages_preserved=True,
                permitted_private_comparison_differences=changes)


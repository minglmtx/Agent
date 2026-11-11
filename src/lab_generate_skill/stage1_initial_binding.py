"""Bind the first actual Actor request before spending inference on a candidate."""
import hashlib
import json

from lab_generate_skill.io_utils import atomic_write_json
from lab_generate_skill.observation_budget import fit_actor_messages


class InitialObservationMismatch(ValueError):
    pass


class InitialObservationGuard:
    def __init__(self, actor, expected_observation, directory):
        if not isinstance(expected_observation, str) or not expected_observation.strip():
            raise ValueError('A captured public initial observation is required')
        self.actor = actor
        self.expected_observation = expected_observation
        self.directory = directory
        self.checked = False

    def __getattr__(self, name):
        return getattr(self.actor, name)

    def generate(self, messages, *, seed):
        if not self.checked:
            counter = getattr(self.actor, 'count_input_tokens', None)
            if counter is None:
                # SharedActorBackend exposes the raw backend, whereas ordinary
                # callers wrap MeasuredActor. Use the exact same tokenizer path.
                counter = lambda value: len(self.actor._tokenizer(self.actor._render(value))['input_ids'])
            selected, budget = fit_actor_messages(messages, counter, 16384)
            users = [m for m in selected if m.get('role') == 'user']
            if not users:
                raise InitialObservationMismatch('The actual first request has no public observation')
            body = json.loads(users[-1]['content'])
            actual = body.get('observation')
            matches = actual == self.expected_observation
            digest = lambda value: hashlib.sha256(value.encode()).hexdigest() if isinstance(value, str) else None
            atomic_write_json(self.directory/'initial-request-binding.json', dict(
                version='stage1-initial-request-binding-v1', equal=matches,
                expected_sha256=digest(self.expected_observation), actual_sha256=digest(actual),
                observation_policy='identity', checked_before_model_call=True,
                model_calls_before_check=0, observation_budget=budget))
            if not matches:
                raise InitialObservationMismatch('Candidate initial request differs from captured context; no model call was made')
            self.checked = True
            messages = selected
        return self.actor.generate(messages, seed=seed)


from pathlib import Path
from lab_generate_skill.shared_actor_backend import SharedActorBackend

class GuardedHolder(SharedActorBackend):
    @classmethod
    def from_holder(cls, holder):
        if holder.backend is not None or holder.sites is not None or holder.closed:
            raise ValueError('Guard holder must be installed before live initialization')
        result = cls()
        result.__dict__.update(holder.__dict__)
        result.pending_guard = None
        return result

    def arm(self, observation, directory):
        if self.pending_guard is not None:
            raise ValueError('Unconsumed initial guard')
        self.pending_guard = (observation, Path(directory))

    def acquire(self, *args, **kwargs):
        backend, created = super().acquire(*args, **kwargs)
        if self.pending_guard is None:
            return backend, created
        expected, directory = self.pending_guard
        self.pending_guard = None
        return InitialObservationGuard(backend, expected, directory), created


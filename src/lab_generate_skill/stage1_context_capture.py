"""Capture a prepared first prompt after the ordinary, verified site reset.

This is a context-only probe, not an actor attempt or a scored training sample.
The actual model is never called. The enclosing ordinary runner closes the
browser and persists its ordinary diagnostic/cleanup evidence.
"""
from .io_utils import atomic_write_json
from .observation_budget import fit_actor_messages


class ContextCaptured(RuntimeError):
    pass


class ContextProbe:
    def __init__(self, actor, directory):
        self.actor = actor
        self.directory = directory
        self.captured = False
        self.last_request_messages = None

    def __getattr__(self, name):
        return getattr(self.actor, name)

    def generate(self, messages, *, seed):
        if self.captured:
            raise RuntimeError("Context probe may prepare only the first prompt")
        messages, budget = fit_actor_messages(messages, self.actor.count_input_tokens, 16384)
        self.last_request_messages = messages
        self.captured = True
        atomic_write_json(self.directory / "prepared-context.json", {
            "status": "context_prepared", "sent_to_model": False,
            "model_calls": 0, "actor_actions": 0, "training_data": False,
            "messages": messages, "seed": seed, "observation_budget": budget,
        })
        raise ContextCaptured("Prepared initial context; no model generation or actor action")

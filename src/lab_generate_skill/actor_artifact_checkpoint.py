"""Optional synchronous sink after a task closes; never performs inference."""
from contextlib import contextmanager
from contextvars import ContextVar

_sink=ContextVar('closed_actor_artifact_sink',default=None)

@contextmanager
def bind_sink(callback):
    token=_sink.set(callback)
    try:yield
    finally:_sink.reset(token)

def save_closed_task(directory):
    callback=_sink.get()
    if callback is not None:callback(directory)

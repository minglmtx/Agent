"""Private evaluator browsing must not activate tabs in the actor context."""
from contextlib import contextmanager


@contextmanager
def private_reference_context(actor_context):
    """Copy current authentication in memory, without actor page event bindings.

    The caller must use its declared local reference URL. Closing this context
    does not close actor tabs or write back cookies/local storage to the actor.
    Site/database effects still require the normal independent state guards.
    """
    browser = actor_context.browser
    if browser is None:
        raise ValueError('Private reference browsing requires an owned Browser')
    reference = browser.new_context(storage_state=actor_context.storage_state())
    try:
        if reference is actor_context:
            raise ValueError('Evaluator context must be distinct from actor context')
        yield reference
    finally:
        if reference is not actor_context:
            reference.close()

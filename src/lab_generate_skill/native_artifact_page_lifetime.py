"""Pure ownership and terminal binding for complete native Hooks.

Initial-page identity proves the declared start only. Subsequent observations
may be a live page in that same owned BrowserContext, including a native new
Tab. No foreign/closed/unowned page or unbound terminal can pass. Missing
terminal data are diagnostic-only when a real runtime failure was recorded;
they never create a successful page, reward, admission or client artifact.
"""

def live_page(hook, page, *, initial=False):
    context = getattr(hook, 'context', None)
    if (not getattr(hook, 'prepared', False) or context is None
            or getattr(hook, 'scored', False) or getattr(hook, 'closed', False)
            or page is None or page.context is not context or page.is_closed()
            or not any(p is page for p in context.pages)):
        raise ValueError('Live Page in the prepared owned BrowserContext required')
    first = getattr(hook, 'initial_page', getattr(hook, 'page', None))
    if not initial and first is None:
        raise ValueError('Declared initial-page proof must precede later observations')
    hook.current_page = page
    return page


def terminal_page(hook, page, terminal):
    live_page(hook, page)
    if (getattr(hook, 'terminal', None) is not None or not isinstance(terminal, dict)
            or terminal.get('url') != page.url):
        raise ValueError('One terminal bound to the actual current live Page required')
    return terminal


def score_bound(hook, site, terminal, runtime_error):
    if not getattr(hook, 'prepared', False) or hook.scored or site is not hook.site:
        raise ValueError('One prepared actual bound-site terminal score required')
    bound = getattr(hook, 'terminal', None)
    if bound is None:
        if terminal is not None or not runtime_error:
            raise ValueError('Missing terminal permits only recorded-runtime-error diagnostics')
        return False
    if terminal != bound:
        raise ValueError('Scoring must retain the complete captured terminal object')
    return not bool(runtime_error)

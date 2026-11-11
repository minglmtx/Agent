"""Validate lifecycle order while retaining interleaved native request evidence."""


def require_lifecycle(events, issued_observations):
    if not isinstance(events, list) or not issued_observations:
        raise ValueError('Complete ordinary native lifecycle required')
    kinds = []
    attached = False
    terminal = False
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get('kind'), str):
            raise ValueError('Malformed native lifecycle event')
        kind = event['kind']
        if kind == 'native_request':
            # The installed observer records only these native auth endpoints.
            # Do not discard or rewrite requests: account-switch judgment still
            # consumes the complete original event stream independently.
            if (not attached or terminal or set(event) != {'kind', 'method', 'path'}
                    or event['path'] not in ('/users/sign_in', '/users/sign_out')
                    or event['method'] not in ('GET', 'POST', 'HEAD', 'DELETE', 'OPTIONS')):
                raise ValueError('Invalid interleaved native request')
            continue
        if kind not in ('prepare', 'attach', 'observe_initial', 'capture', 'record',
                        'capture_chat', 'capture_terminal', 'score_terminal'):
            raise ValueError('Unexpected native lifecycle event')
        kinds.append(kind)
        if kind == 'attach':
            attached = True
        if kind == 'capture_terminal':
            terminal = True
    boundaries = ('prepare', 'attach', 'observe_initial', 'capture_chat',
                  'capture_terminal', 'score_terminal')
    if (any(kinds.count(k) != 1 for k in boundaries)
            or kinds[:3] != list(boundaries[:3])
            or kinds[-3:] != list(boundaries[-3:])):
        raise ValueError('Complete ordered native lifecycle required')
    middle = kinds[3:-3]
    if not middle or len(middle) % 2 or middle != ['capture', 'record'] * (len(middle) // 2):
        raise ValueError('Each native capture must have its corresponding record')
    return True

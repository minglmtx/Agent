"""Read-only explicit light/dark preference; automatic themes need separate evidence."""
from urllib.parse import urlsplit, quote
from .site_preferences_rules import preference_state


def validate(q):
    if (q.get('family') != 'reddit_theme' or q.get('fields') != {'dark_mode': 'string'} or
            not isinstance(q.get('username'), str) or not q['username'] or
            type(q.get('object_id')) is not int or q['object_id'] <= 0):
        raise ValueError('Invalid theme query')
    if q['reference_path'] != '/user/'+quote(q['username'], safe='')+'/preferences':
        raise ValueError('Theme reference is not the requested account preferences')


def value(mode):
    if mode not in ('light', 'dark'):
        raise ValueError('Automatic theme requires independent browser/system preference evidence')
    return {'dark_mode': 'yes' if mode == 'dark' else 'no'}


def reference(site, q):
    validate(q)
    state = preference_state(site, q['username'])
    if state['user_id'] != q['object_id']:
        raise ValueError('Theme account identity changed')
    return {'object_id': 'reddit-theme:'+str(q['object_id']),
            'values': value(state['values']['night_mode']), 'source_state': state}


def ui_values(page, q):
    validate(q)
    u = urlsplit(page.url)
    if u.path != q['reference_path'] or u.query:
        raise ValueError('Wrong preferences page')
    account = page.get_by_role('button', name=q['username'], exact=True)
    if account.count() != 1 or not account.is_visible():
        raise ValueError('Current account not independently visible')
    control = page.locator('#user_settings_nightMode')
    if control.count() != 1 or not control.is_visible():
        raise ValueError('Native Night mode selection not visible')
    labels = control.evaluate('e => [...e.labels].map(l=>l.innerText.trim())')
    if labels != ['Night mode']:
        raise ValueError('Unexpected native preference label')
    return value(control.input_value())

"""Explicit navigation to native authentication forms, not authenticated access.

Profiles describe public form structure. They contain no account credentials,
expected answers, or actor actions. Other navigation tasks still reject login.
"""
from copy import deepcopy

PROFILES = {
    'openid_form': {'path_regex': '/login/?', 'heading_regex': '^Login$',
                    'visible_form': {'fields': ['openid_url'], 'submit_text': 'Login'}},
    'login': {'path_regex': '/login/?', 'heading_regex': '^Login$',
              'visible_form': {'fields': ['username', 'password'], 'submit_text': 'Login'}},
    'signup': {'path_regex': '/user/new/?', 'heading_regex': '^Sign Up$',
               'visible_form': {'fields': ['user[email]', 'user[email_confirmation]',
                   'user[display_name]', 'user[pass_crypt]', 'user[pass_crypt_confirmation]'],
                   'submit_text': 'Sign Up'}},
    'recovery': {'path_regex': '/user/forgot-password/?', 'heading_regex': r'^Forgotten Password\?$',
                 'visible_form': {'fields': ['email'], 'submit_text': 'Reset password'}},
}


def completion(kind):
    return deepcopy(PROFILES[kind]) | {'authentication_page': kind}


def validate(contract):
    expected = contract['completion']
    kind = expected.get('authentication_page')
    if not isinstance(kind, str) or kind not in PROFILES or contract.get('domain') != 'map':
        raise ValueError('Unsupported native authentication-page profile')
    if any(expected.get(k) != v for k, v in PROFILES[kind].items()):
        raise ValueError('Authentication-page navigation requires its native path, heading and complete form')
    if expected.get('identity_source', 'heading') != 'heading':
        raise ValueError('Authentication-page identity must use its heading')
    return kind


def login_is_target(contract):
    if not contract['completion'].get('authentication_page'):
        return False
    return validate(contract) == 'login'


def login_document_allowed(contract):
    """Permit this document only for an explicit native form goal.

    This is separate from whether the default, collapsed /login page is already
    a positive control. Opening OpenID is never proof of third-party identity.
    """
    if not contract['completion'].get('authentication_page'):
        return False
    return validate(contract) in ('login','openid_form')


def open_form_control(page,contract):
    """Private CPU positive control only; never called by the actor runner."""
    if validate(contract)!='openid_form':
        raise ValueError('Explicit OpenID form control required')
    from urllib.parse import urlsplit
    if urlsplit(page.url).path.rstrip('/')!='/login':
        raise ValueError('Native login page required before control')
    field=page.locator('#openid_login_form input[name="openid_url"]')
    if field.count()!=1:raise ValueError('Unique native OpenID field required')
    if not field.is_visible():
        link=page.locator('#openid_open_url')
        if link.count()!=1 or not link.is_visible():raise ValueError('Visible native OpenID option required')
        link.click(timeout=10000)
    field.wait_for(state='visible',timeout=10000)

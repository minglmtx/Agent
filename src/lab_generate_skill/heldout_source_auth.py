"""Bind source login state from the selected first observation, not its URL."""
import ast
import re
from urllib.parse import urlsplit

from .heldout_initial_controls import QUOTED
from .heldout_initial_state import fingerprint

VERSION = 'heldout-source-auth-v1'
NODE = re.compile(r'^\s*(?:\[\d+\]\s+)?(?P<role>\w+)\s+(?P<name>' + QUOTED + r')(?P<attrs>.*)$')
URL = re.compile(r'\burl=(' + QUOTED + r')')


def reddit_source_authentication(frame):
    """Require header evidence; a viewed profile or login URL proves nothing."""
    links, menus, header = [], [], []
    saw_main = False
    for line in frame['observation']['axtree'].splitlines():
        match = NODE.fullmatch(line)
        if match is None:
            continue
        if match['role'] == 'main':
            saw_main = True
            break
        header.append(line)
        role, name, attrs = match['role'], ast.literal_eval(match['name']), match['attrs']
        if role == 'link':
            url = URL.search(attrs)
            if url:
                links.append((name, urlsplit(ast.literal_eval(url[1])).path))
        if role == 'button' and "hasPopup='menu'" in attrs:
            menus.append(name)
    anonymous = ('Log in', '/login') in links and ('Sign up', '/registration') in links
    # The benchmark username is a public UI account identity, not a credential.
    known_user = menus == ['MarvelsGrantMan136']
    mode = 'anonymous' if anonymous and not menus else 'authenticated' if known_user and not anonymous else 'unknown'
    if not saw_main:
        mode = 'unknown'
    return dict(version=VERSION, mode=mode, username='MarvelsGrantMan136' if mode == 'authenticated' else None,
        selected_trace_id=frame['trace_id'], observation_sha256=fingerprint(frame['observation']),
        evidence_scope='navigation header before the first main region',
        header_sha256=fingerprint(header), login_signup_links_present=anonymous, account_menu_names=menus)


def shopping_source_authentication(frame):
    """Retain source account and cart labels; a logout URL is not auth proof.

    This binds observed header state only. A welcome name cannot establish a
    database account ID, and an absent cart count cannot be assumed to mean zero.
    """
    links, welcomes, cart_labels, header = [], set(), [], []
    saw_main = False
    for line in frame['observation']['axtree'].splitlines():
        match = NODE.fullmatch(line)
        if match is None: continue
        if match['role'] == 'main':
            saw_main = True
            break
        header.append(line)
        role, name, attrs = match['role'], ast.literal_eval(match['name']), match['attrs']
        welcome = re.fullmatch(r'Welcome, (.+)!', name)
        if welcome: welcomes.add(welcome[1])
        if role == 'link':
            url = URL.search(attrs)
            if url:
                path = urlsplit(ast.literal_eval(url[1])).path
                links.append((name, path))
                if path == '/checkout/cart/' and 'My Cart' in name:
                    cart_labels.append(name)
    signed_out = ('Sign In', '/customer/account/login/') in links
    signed_in = ('Sign Out', '/customer/account/logout/') in links
    mode = ('authenticated' if signed_in and not signed_out and len(welcomes) == 1 else
            'anonymous' if signed_out and not signed_in and not welcomes else 'unknown')
    if not saw_main: mode = 'unknown'
    return dict(version=VERSION, mode=mode, welcome_names=sorted(welcomes), cart_labels=cart_labels,
        selected_trace_id=frame['trace_id'], observation_sha256=fingerprint(frame['observation']),
        evidence_scope='header before the first main region', header_sha256=fingerprint(header),
        database_account_identity_verified=False, cart_contents_verified=False)

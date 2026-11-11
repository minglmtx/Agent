"""CPU acceptance controls for a public forward link actually issued in AX.

This module never finds a private answer or changes the actor's strategy. A
control may select only the current page's issued link, preserve its recorded
public target, and execute it through the ordinary action parser and session.
"""
import json
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from .public_read_memory import MEMORY_MARKER, current_observation_bids


def issued_forward_link(page, observation, expected_url):
    """Return a current issued More/Next bid, or None when it is not exposed.

    Browser AX names normalize HTML whitespace. Looking for a raw inner-text
    regex such as ``^More$`` can miss the native link even when AX contains it.
    Use the issued AX bid, then verify the actual native href instead.
    """
    current, target = urlsplit(page.url), urlsplit(expected_url)
    if ((current.scheme, current.netloc) != (target.scheme, target.netloc)
            or target.scheme not in ('http', 'https') or target.username
            or target.password):
        raise ValueError('Forward pagination must retain the current public site')
    text = observation.get('axtree_txt', '')
    if not isinstance(text, str):
        raise ValueError('Actual issued accessibility-tree text required')
    text = text.rsplit('\n\n' + MEMORY_MARKER, 1)[0]
    issued = current_observation_bids(observation)
    matches = re.findall(
        r'(?mi)^[ \t]*\[([^\]\s]+)\][ \t]+link[ \t]+[\'"](More|Next)[\'"](?:,.*)?$',
        text,
    )
    links = []
    for bid, _ in matches:
        if bid not in issued or not re.fullmatch(r'[A-Za-z0-9_.:-]+', bid):
            raise ValueError('Actual current safe pagination bid required')
        link = page.locator('a[bid="' + bid + '"][href]')
        if link.count() != 1:
            raise ValueError('Issued pagination bid must identify one native link')
        href = urljoin(page.url, link.get_attribute('href'))
        if href == expected_url:
            links.append((bid, link))
    if not matches:
        return None
    if len(links) != 1:
        raise ValueError('Current issued forward link changed or duplicated its public target')
    bid, link = links[0]
    link.wait_for(state='visible', timeout=5000)
    return bid


def advance_public_page(session, issuer, expected_url, *, max_scrolls=8):
    """Issue the same real parsed click used by ordinary browser execution."""
    if type(max_scrolls) is not int or max_scrolls <= 0:
        raise ValueError('Positive bounded public exposure limit required')
    for _ in range(max_scrolls):
        obs = issuer.requests[-1]['observation'] if issuer.requests else {}
        bid = issued_forward_link(session.env.page, obs, expected_url)
        if bid is not None:
            reply = json.dumps({'thought': 'CPU native public pagination control.',
                                'action': 'click', 'args': [bid]})
            action, _ = issuer.protocol.parse(reply, obs)
            issuer.step(session, action)
            actual, expected = urlsplit(session.env.page.url), urlsplit(expected_url)
            shape = lambda url: (url.scheme, url.netloc, url.path,
                                  parse_qs(url.query, keep_blank_values=True))
            if shape(actual) != shape(expected):
                raise ValueError('Public parsed pagination action reached another native page')
            return
        before = session.env.page.evaluate('() => scrollY')
        issuer.step(session, 'scroll(0, 700)')
        if session.env.page.evaluate('() => scrollY') <= before:
            raise ValueError('Forward pagination bid absent from actual selected public AX at page bottom')
    raise ValueError('Bounded actual public forward pagination exposure unavailable')

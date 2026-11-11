"""Private native artifact probe helpers; no actor execution or admission."""
import hashlib
from urllib.parse import urlsplit, urlunsplit
import re
from .gitlab_local_artifacts_v2 import MAX_FEED_BYTES, redacted_url


def unique_native_control(page, names, *, failure):
    """Use native accessible names, including link dropdowns and icon buttons."""
    controls = []
    for role in ('button', 'link'):
        controls.extend(control for control in page.get_by_role(role, name=names).all() if control.is_visible())
    if len(controls) != 1: raise ValueError(failure)
    return controls[0]


def unique_heading_link(page, title):
    """Locate a native card by its heading, not its combined accessible name.

    GitLab includes the card's explanatory paragraph in the link name. This
    helper is for CPU controls only; it never selects an action for the actor.
    """
    if not isinstance(title, str) or not title.strip():
        raise ValueError('A nonempty native card heading is required')
    heading = page.get_by_role('heading', name=title, exact=True)
    links = page.get_by_role('link').filter(has=heading)
    visible = [link for link in links.all() if link.is_visible()]
    if len(visible) != 1:
        raise ValueError('Expected one visible link containing heading ' + repr(title)
                         + '; found ' + str(len(visible)))
    return visible[0]


def native_template_choice(page, template_id, title):
    """Return the real label for an independently qualified native template.

    GitLab's picker uses a visually hidden radio and a visible label, not a
    button. Verify identity and the enclosing single-radio card's exact title
    before following that label. This is only a CPU control helper.
    """
    if not all(isinstance(x, str) and x.strip() for x in (template_id, title)):
        raise ValueError('A qualified template identity and exact title are required')
    radios = [r for r in page.locator('input[type="radio"]').all()
              if r.get_attribute('value') == template_id]
    if len(radios) != 1:
        raise ValueError('Expected one native template radio for ' + repr(template_id))
    radio = radios[0]
    matches = radio.evaluate('''(radio, title) => {
        for (let card = radio.parentElement; card; card = card.parentElement) {
            if (card.querySelectorAll('input[type="radio"]').length !== 1) break;
            const titles = [...card.querySelectorAll('strong,h1,h2,h3,h4,h5,h6')];
            if (titles.some(t => t.textContent.trim() === title)) return true;
        }
        return false;
    }''', title)
    if matches is not True or not radio.is_enabled():
        raise ValueError('Native template radio does not match its exact card title')
    identity = radio.get_attribute('id')
    labels = []
    for label in page.locator('label').all():
        associated = bool(identity and label.get_attribute('for') == identity)
        if not associated:
            associated = label.evaluate('(label, radio) => label.contains(radio)', radio.element_handle())
        if (associated and label.is_visible()
                and label.inner_text().strip() in ('Use template', 'Use this template')):
            labels.append(label)
    if len(labels) != 1:
        raise ValueError('Expected one visible label for the qualified template radio')
    return labels[0]


def select_native_radio(page, name, value, *, timeout=10000):
    """CPU controls: select a radio through its real visible associated label.

    Do not force clicks or modify DOM state. A styled label may legitimately
    cover the input; verify the checked state after normal browser interaction.
    """
    if not all(isinstance(x, str) and x for x in (name, value)):
        raise ValueError('Radio name and value are required')
    radios = [r for r in page.locator('input[type="radio"]').all()
              if r.get_attribute('name') == name and r.get_attribute('value') == value]
    labels = page.locator('label').all()
    candidates = []
    for radio in radios:
        if not radio.is_enabled():
            continue
        handle = radio.element_handle()
        associated = [label for label in labels if label.is_visible() and
                      label.evaluate('(label, radio) => label.control === radio', handle)]
        # Hidden inactive forms may duplicate the same name/value. The real
        # DOM label.control relation also disambiguates repeated HTML ids.
        if associated or radio.is_visible():
            candidates.append((radio, associated))
    if len(candidates) != 1:
        raise ValueError('Expected one enabled interactable native radio for ' +
                         repr((name, value)) + '; matched=' + str(len(radios)) +
                         ', interactable=' + str(len(candidates)))
    radio, labels = candidates[0]
    if len(labels) > 1:
        raise ValueError('Native radio has no unique visible interaction target')
    if radio.is_checked():
        return
    if labels:
        labels[0].click(timeout=timeout)
    elif radio.is_visible():
        radio.check(timeout=timeout)
    else:
        raise ValueError('Native radio has no visible interaction target')
    if not radio.is_checked():
        raise ValueError('Native radio did not retain the requested selection')


def fill_native_field(locator, value, *, timeout=10000):
    """CPU control entry: commit change/blur before inspecting the next field."""
    if not isinstance(value, str):
        raise ValueError('Explicit native field text required')
    locator.fill(value, timeout=timeout)
    locator.press('Tab', timeout=timeout)
    if locator.input_value(timeout=timeout) != value:
        raise ValueError('Native field changed after committing public input')


def response_shape(response, kind):
    """Diagnose HTTP/parser failures without persisting secrets or body text."""
    body = response.body()
    headers = response.headers
    result = {'http_status': response.status, 'content_type': headers.get('content-type'),
              'body_bytes': len(body), 'body_sha256': hashlib.sha256(body).hexdigest(),
              'within_feed_budget': 0 < len(body) <= MAX_FEED_BYTES,
              'response_body_and_credentials_not_saved': True, 'kind': kind,
              'redirect_location': redacted_url(headers['location']) if headers.get('location') else None}
    if len(body) > MAX_FEED_BYTES: return result
    text = body.decode('utf-8-sig', errors='replace')
    lines = text.replace('\r\n', '\n').splitlines()
    nonempty = [line for line in lines if line.strip()]
    result['body_shape'] = {'has_calendar_begin': any(line == 'BEGIN:VCALENDAR' for line in lines),
        'has_calendar_end': any(line == 'END:VCALENDAR' for line in lines),
        'calendar_first_nonempty_is_begin': bool(nonempty and nonempty[0] == 'BEGIN:VCALENDAR'),
        'calendar_last_nonempty_is_end': bool(nonempty and nonempty[-1] == 'END:VCALENDAR'),
        'calendar_version_2': 'VERSION:2.0' in lines,
        'leading_blank_lines': len(lines) - len(text.lstrip('\r\n \t').splitlines()),
        'xml_declaration': text.lstrip().startswith('<?xml'),
        'has_atom_namespace': 'http://www.w3.org/2005/Atom' in text,
        'looks_like_html': bool(re.search(r'<(?:html|head|body)(?:\s|>)', text, re.I))}
    return result


def normalize_artifact_reference(reference, origin):
    """Strip only this fresh site's exact ephemeral origin from native IDs.

    Arbitrary external identities, query, fragment and resource paths retain
    their values. Repository HEAD/tree and other private fields are unchanged.
    """
    if reference is None: return None
    normalized = dict(reference)
    if 'entry_ids' in normalized:
        expected = urlsplit(origin)
        ids = []
        for value in normalized['entry_ids']:
            part = urlsplit(value)
            if (part.scheme, part.netloc) == (expected.scheme, expected.netloc):
                value = 'local:' + urlunsplit(('', '', part.path, part.query, part.fragment))
            ids.append(value)
        normalized['entry_ids'] = ids
    return normalized

"""Private Atom payload checks against independently captured native rows.

This does not check that a subscription was saved, or grant task admission.
The caller must bind database references to the same site, account and state
as the fetch. Missing page references remain incomplete, not actor failure.
Reference rows and expected IDs must never be included in actor observations.
"""
from collections import Counter
from datetime import date
import re
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET

from .gitlab_local_artifacts_v2 import local_native_url, parse_feed

ATOM = '{http://www.w3.org/2005/Atom}'


def inspect_atom_reference(payload, *, origin, project_path, project_id,
                           collection, filters, rows, expected_page_iids=None):
    """Check scope, full titles and (when independently known) page membership.

    ``rows`` is the complete native project collection, not rows selected using
    the response. ``expected_page_iids`` comes from the native selection query,
    including the authenticated user's sorting preferences and pagination.
    The native Atom builder truncates titles; its summary holds the full title.
    Only credential query values are ignored. Extra filters cannot silently
    narrow a subscription. Reports contain no response text or credentials.
    """
    if collection not in ('issues', 'merge_requests'):
        raise ValueError('Unsupported native Atom collection')
    if filters != {'state': ['opened']}:
        raise ValueError('Only the declared open-collection scope is implemented')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+', project_path):
        raise ValueError('Invalid declared project path')
    if type(project_id) is not int or project_id <= 0:
        raise ValueError('A native project identity is required')
    project_field = 'target_project_id' if collection == 'merge_requests' else 'project_id'
    by_iid = {}
    for row in rows:
        iid = row.get('iid')
        if (type(iid) is not int or iid <= 0 or iid in by_iid
                or row.get(project_field) != project_id
                or type(row.get('state_id')) is not int
                or not isinstance(row.get('title'), str)):
            raise ValueError('Native reference rows are ambiguous or outside project scope')
        by_iid[iid] = row
    if expected_page_iids is not None:
        if (not isinstance(expected_page_iids, list)
                or any(type(i) is not int or i not in by_iid or by_iid[i]['state_id'] != 1
                       for i in expected_page_iids)
                or len(set(expected_page_iids)) != len(expected_page_iids)):
            raise ValueError('Invalid independent native page reference')
    checks = dict.fromkeys(('valid_atom', 'feed_identity', 'self_link_scope',
                            'entry_objects', 'entry_open_state', 'entry_full_titles'), False)
    report = {'checks': checks, 'entry_count': None,
              'reference_page_available': expected_page_iids is not None,
              'page_membership_matches': None, 'payload_verified': False,
              'subscription_verified': False, 'training_admitted': False}
    base = '/' + project_path + '/-/' + collection

    def resource(value):
        return urlsplit(local_native_url(value, origin))

    try:
        parse_feed(payload, 'atom')
        root = ET.fromstring(payload)
        checks['valid_atom'] = True
        ident = resource(root.findtext(ATOM + 'id'))
        checks['feed_identity'] = ident.path == base and not ident.query
        links = [n for n in root.findall(ATOM + 'link') if n.get('rel') == 'self']
        if len(links) == 1 and links[0].get('href'):
            link = resource(links[0].get('href'))
            query = parse_qs(link.query, keep_blank_values=True)
            query.pop('feed_token', None)
            checks['self_link_scope'] = link.path == base + '.atom' and query == filters
        entries = root.findall(ATOM + 'entry')
        report['entry_count'] = len(entries)
        actual = []
        valid_objects = valid_states = valid_titles = True
        for entry in entries:
            target = resource(entry.findtext(ATOM + 'id'))
            match = re.fullmatch(re.escape(base) + r'/([1-9][0-9]*)', target.path)
            row = None
            if match and not target.query:
                iid = int(match[1]); actual.append(iid); row = by_iid.get(iid)
            if row is None:
                valid_objects = valid_states = valid_titles = False
                continue
            valid_states &= row['state_id'] == 1
            summaries = entry.findall(ATOM + 'summary')
            valid_titles &= (len(summaries) == 1 and not list(summaries[0])
                             and summaries[0].text == row['title'])
        checks.update(entry_objects=valid_objects, entry_open_state=valid_states,
                      entry_full_titles=valid_titles)
        if expected_page_iids is not None:
            report['page_membership_matches'] = Counter(actual) == Counter(expected_page_iids)
        report['payload_verified'] = all(checks.values()) and report['page_membership_matches'] is True
    except (ValueError, TypeError, ET.ParseError):
        report['invalid_payload_or_resource'] = True
    return report


def inspect_calendar_reference(payload, *, origin, rows):
    """Check native event content against the independently selected issues.

    The installed template emits an all-day DTSTART, full summary and URL for
    each issue. It generates event UIDs at rendering time, so UIDs are checked
    for uniqueness by the parser, not compared across two separate fetches.
    Native account, date-window, archive and permission selection is the
    reference collector's responsibility; an absent reference is an error.
    """
    if not isinstance(rows, list):
        raise ValueError('Independent calendar selection required, including an explicit empty list')
    expected = {}
    for row in rows:
        try:
            path = '/' + row['project_path'] + '/-/issues/' + str(row['iid'])
            due = date.fromisoformat(row['due_date']).strftime('%Y%m%d')
            if type(row['iid']) is not int or row['iid'] <= 0 or path in expected:
                raise ValueError('Ambiguous calendar reference')
            if not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+', row['project_path']):
                raise ValueError('Invalid calendar project')
            if row['state_id'] != 1 or not isinstance(row['title'], str):
                raise ValueError('Calendar reference is not an open issue')
            expected[path] = (due, row['title'] + ' (in ' + row['project_path'] + ')')
        except (KeyError, TypeError, ValueError):
            raise ValueError('Malformed native calendar reference') from None
    checks = dict.fromkeys(('valid_calendar', 'exact_event_objects', 'event_dates', 'event_summaries'), False)
    report = {'checks': checks, 'event_count': None, 'payload_verified': False,
              'subscription_verified': False, 'training_admitted': False}

    def text_value(value):
        # iCalendar TEXT escaping. Do not perform HTML unescaping or trim titles.
        def unescape(match):
            char = match[1]
            if char is None or char not in 'nN,;\\':
                raise ValueError('Invalid calendar text escape')
            return '\n' if char in 'nN' else char
        return re.sub(r'\\(.)|\\$', unescape, value)

    try:
        parse_feed(payload, 'calendar')
        checks['valid_calendar'] = True
        lines = []
        for line in payload.decode('utf-8-sig').splitlines():
            if line.startswith((' ', '\t')) and lines:
                lines[-1] += line[1:]
            else:
                lines.append(line)
        events, current = [], None
        for line in lines:
            if line == 'BEGIN:VEVENT':
                current = {}
            elif line == 'END:VEVENT':
                events.append(current); current = None
            elif current is not None:
                name, value = line.split(':', 1)
                key = name.split(';', 1)[0]
                if key in current or key in ('BEGIN', 'END'):
                    raise ValueError('Ambiguous event properties')
                current[key] = (name, value)
        report['event_count'] = len(events)
        actual = []
        dates = summaries = True
        for event in events:
            target = urlsplit(local_native_url(event['URL'][1], origin))
            actual.append(target.path)
            reference = expected.get(target.path)
            if target.query or reference is None:
                dates = summaries = False
                continue
            dates &= event['DTSTART'] == ('DTSTART;VALUE=DATE', reference[0])
            summaries &= text_value(event['SUMMARY'][1]) == reference[1]
        checks.update(exact_event_objects=Counter(actual) == Counter(expected.keys()),
                      event_dates=dates, event_summaries=summaries)
        report['payload_verified'] = all(checks.values())
    except (ValueError, TypeError, KeyError):
        report['invalid_payload_or_resource'] = True
    return report

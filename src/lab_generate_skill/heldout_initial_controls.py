"""Compare source-visible form state with native CDP AX captures.

This is an initialization diagnostic, not a full equivalence certificate. It
does not establish document contents, collection completeness, browser storage,
or task-specific object identity. Ambiguous controls require further binding.
"""
import ast
from collections import Counter
import json
import re
from urllib.parse import urlsplit

VERSION = 'heldout-initial-controls-v1'
ROLES = ('textbox', 'searchbox', 'combobox', 'checkbox', 'radio', 'listbox', 'option', 'spinbutton')
QUOTED = r'''(?:'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")'''
LINE = re.compile(r'^\s*(?:\[\d+\]\s+)?(?P<role>' + '|'.join(ROLES) +
                  r')\s+(?P<name>' + QUOTED + r')(?P<attrs>.*)$')
ROLE_LINE = re.compile(r'^\s*(?:\[\d+\]\s+)?(?:' + '|'.join(ROLES) + r')\b')
ATTR = re.compile(r'\b(value|checked|selected|disabled|readonly|required|expanded)=(' + QUOTED + r'|True|False)')


def normalize(value):
    if value in ('true', 'false'):
        return value == 'true'
    return value


def control(role, name, values):
    # No focus normalization: focus is outside this limited diagnostic scope.
    result = dict(role=role, name=name, disabled=normalize(values.get('disabled', False)),
                  required=normalize(values.get('required', False)), readonly=normalize(values.get('readonly', False)))
    if role in ('textbox', 'searchbox', 'combobox', 'spinbutton'):
        result['value'] = str(values.get('value', ''))
    if role in ('checkbox', 'radio'):
        result['checked'] = normalize(values.get('checked', False))
    if role == 'option':
        result['selected'] = normalize(values.get('selected', False))
    if 'expanded' in values:
        result['expanded'] = normalize(values['expanded'])
    return result


def source_controls(axtree):
    if not isinstance(axtree, str):
        raise ValueError('Source AX text required')
    controls, unparsed = [], []
    for line in axtree.splitlines():
        if not ROLE_LINE.match(line):
            continue
        match = LINE.fullmatch(line)
        if not match:
            unparsed.append(line)
            continue
        attrs = match['attrs']
        values = {key: ast.literal_eval(value) for key, value in ATTR.findall(attrs)}
        if re.search(r'(?:^|,)\s*required\s*(?:,|$)', attrs):
            values['required'] = True
        controls.append(control(match['role'], ast.literal_eval(match['name']), values))
    return controls, unparsed


def native_controls(nodes):
    if not isinstance(nodes, list) or not nodes:
        raise ValueError('Nonempty native AX nodes required')
    result = []
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get('role'), dict):
            raise ValueError('Malformed native AX node')
        if node.get('ignored') is True:
            continue
        role = node['role'].get('value')
        if role not in ROLES:
            continue
        name = node.get('name', {}).get('value', '')
        if not isinstance(name, str):
            raise ValueError('Malformed native control name')
        values = {}
        for prop in node.get('properties', []):
            if not isinstance(prop, dict) or not isinstance(prop.get('value'), dict):
                raise ValueError('Malformed native control property')
            values[prop['name']] = prop['value'].get('value')
        if 'value' in node:
            values['value'] = node['value'].get('value', '')
        result.append(control(role, name, values))
    return result


def local_path(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError('Ordinary website document URL required')
    return (parsed.path or '/') + ('?' + parsed.query if parsed.query else '') + ('#' + parsed.fragment if parsed.fragment else '')


def compare(frame, page, *, site_origin):
    """Ignore deployment origin only; keep business queries and fragments exact."""
    source, unparsed = source_controls(frame['observation']['axtree'])
    native = native_controls(page['native_ax_nodes'])
    actual, origin = urlsplit(page['url']), urlsplit(site_origin)
    same_site = (actual.scheme, actual.netloc) == (origin.scheme, origin.netloc)
    same_route = local_path(frame['original_url']) == local_path(page['url'])
    key = lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False)
    wanted, found = Counter(map(key, source)), Counter(map(key, native))
    missing = [json.loads(k) for k in (wanted - found).elements()]
    extra = [json.loads(k) for k in (found - wanted).elements()]
    identities = Counter((r['role'], r['name']) for r in source)
    ambiguous = [dict(role=role, name=name, count=count) for (role, name), count in identities.items() if count > 1]
    status = ('unverifiable' if unparsed or ambiguous else
              'match' if same_site and same_route and not missing and not extra else 'mismatch')
    return dict(version=VERSION, scope='original_route_and_visible_form_controls_only',
                status=status, same_site=same_site, same_route=same_route,
                source_control_count=len(source), native_control_count=len(native),
                missing_or_changed_controls=missing, extra_or_changed_controls=extra,
                ambiguous_source_controls=ambiguous, unparsed_source_lines=unparsed,
                full_initial_equivalence_verified=False, evaluation_ready=False)

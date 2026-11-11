"""Offline diagnostic of ordered accessible names in original/native pages.

This detects missing business content without using answers or trajectories.
It does not certify visual/layout equivalence, links, storage, or form values.
Relative timestamps and other differences are reported, never erased to pass.
"""
import ast
from collections import Counter
import re

from .heldout_initial_controls import QUOTED

VERSION = 'heldout-initial-document-v1'
LINE = re.compile(r'^\s*(?:\[\d+\]\s+)?(?P<role>[A-Za-z][A-Za-z0-9_-]*)\s+(?P<name>' + QUOTED + r')(?P<attrs>.*)$')
# BrowserGym deliberately omits the quoted name for an unnamed generic node.
# Properties (including rendered_text) still carry content and must survive.
NAMELESS_GENERIC = re.compile(r'^\s*(?:\[\d+\]\s+)?generic(?P<attrs>(?: value=' + QUOTED + r')?(?:, .*)?)$')
PREFIX = re.compile(r'^(?P<indent>\s*)(?:\[(?P<bid>\d+)\]\s+)?')
# These are structural wrappers/glyph fragments, not semantic content roles.
# Every removal is counted in the diagnostic. Named wrappers remain visible.
WRAPPERS = frozenset(('generic', 'none'))


def keep(role, name):
    return role != 'InlineTextBox' and not (role in WRAPPERS and not name)


def source_records(text):
    """Parse rendered AX records without dropping text, order, or attributes.

    ``attributes_text`` is retained verbatim, not interpreted or normalized.
    This is a diagnostic representation; matching it never certifies full
    initial-state equivalence. The caller must retain the complete input too.
    """
    rows, unparsed = [], []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        match = LINE.fullmatch(line)
        nameless = False
        if not match:
            match = NAMELESS_GENERIC.fullmatch(line)
            nameless = match is not None
        if not match:
            unparsed.append(line)
            continue
        role, name = ('generic', '') if nameless else (match['role'], ast.literal_eval(match['name']))
        prefix = PREFIX.match(line)
        rows.append(dict(line_number=number, raw=line, indent=prefix['indent'],
                         bid=prefix['bid'], role=role, name=name,
                         name_was_quoted=not nameless, attributes_text=match['attrs']))
    return rows, unparsed


def source_sequence(text):
    records, unparsed = source_records(text)
    rows, omitted = [], Counter()
    for record in records:
        role, name = record['role'], record['name']
        if keep(role, name):
            rows.append((role, name))
        else:
            omitted[role] += 1
    return rows, unparsed, dict(omitted)


def native_sequence(nodes):
    """CDP node arrays are not guaranteed to be in document order: follow edges."""
    if not isinstance(nodes, list) or not nodes:
        raise ValueError('Complete native accessibility tree required')
    by_id, duplicate_glyphs, duplicate_dom_records = {}, 0, 0
    for node in nodes:
        key = node['nodeId']
        if key in by_id:
            # Chromium repeats glyph records and native select option records.
            # A repeated semantic record is safe to index once only when every
            # field agrees AND it identifies the same actual backend DOM node.
            # Tree traversal below still rejects shared semantic child edges.
            if node != by_id[key]:
                raise ValueError('Duplicate native accessibility node')
            if node.get('role', {}).get('value') == 'InlineTextBox':
                duplicate_glyphs += 1
            elif type(node.get('backendDOMNodeId')) is int and node['backendDOMNodeId'] > 0:
                duplicate_dom_records += 1
            else:
                raise ValueError('Duplicate native accessibility node without DOM identity')
        else:
            by_id[key] = node
    roots = [n for n in by_id.values() if n.get('parentId') not in by_id]
    if len(roots) != 1 or roots[0].get('role', {}).get('value') != 'RootWebArea':
        raise ValueError('Exactly one complete document accessibility root required')
    seen, rows, omitted = set(), [], Counter()
    omitted['duplicate_inline_textbox_records'] = duplicate_glyphs
    omitted['duplicate_identical_dom_node_records'] = duplicate_dom_records
    pending = [roots[0]['nodeId']]
    while pending:
        key = pending.pop()
        if key in seen and by_id[key].get('role', {}).get('value') == 'InlineTextBox':
            omitted['duplicate_inline_textbox_edges'] += 1
            continue
        if key in seen or key not in by_id:
            raise ValueError('Accessibility child missing, cyclic, or shared')
        seen.add(key)
        node = by_id[key]
        role, name = node.get('role', {}).get('value'), node.get('name', {}).get('value', '')
        if not isinstance(role, str) or not isinstance(name, str):
            raise ValueError('Malformed native accessible name')
        if node.get('ignored') is True:
            omitted['ignored'] += 1
        elif keep(role, name):
            rows.append((role, name))
        else:
            omitted[role] += 1
        pending.extend(reversed(node.get('childIds', [])))
    if seen != set(by_id):
        raise ValueError('Native accessibility nodes disconnected from root')
    return rows, dict(omitted)


def compare_document(frame, page):
    source, unparsed, source_omitted = source_sequence(frame['observation']['axtree'])
    native, native_omitted = native_sequence(page['native_ax_nodes'])
    wanted, actual = Counter(source), Counter(native)
    def differences(counts):
        return [dict(role=role, name=name, count=count) for (role, name), count in counts.items()]
    return dict(version=VERSION, scope='ordered_accessible_roles_and_names_only',
        status='unverifiable' if unparsed else 'match' if source == native else 'mismatch',
        source_nodes=len(source), native_nodes=len(native), same_ordered_sequence=source == native,
        missing_or_changed= differences(wanted - actual), extra_or_changed=differences(actual - wanted),
        source_omitted=source_omitted, native_omitted=native_omitted, unparsed_source_lines=unparsed,
        full_initial_equivalence_verified=False, evaluation_ready=False)

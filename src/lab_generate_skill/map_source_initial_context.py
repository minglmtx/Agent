"""Read declared Map starting context from the first source observation only.

This is preparation evidence, not an environment reference or task verdict.
An absent route/view must be explicitly initialized or left unresolved; later
actor choices never supply a missing original target.
"""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from .map_metadata_query import initial_view
from .map_route_initialization_binding import initial_url_state
from .source_revision_binding import exact_local_path, local_path


def context(trace, *, task_id, goal):
    if trace.get('domain') != 'map' or trace.get('task_id') != task_id or trace.get('task_instruction') != goal:
        raise ValueError('Original task identity and goal required')
    messages = trace.get('messages')
    if not isinstance(messages, list) or not messages:
        raise ValueError('First source observation missing')
    first = messages[0]
    if first.get('role') != 'user' or type(first.get('turn')) is not int or first['turn'] != 0:
        raise ValueError('Must use the initial observation, not a later actor state')
    observation = json.loads(first['content'])
    ax = observation.get('axtree')
    if not isinstance(ax, str) or not ax.splitlines():
        raise ValueError('Initial accessibility tree missing')
    header = ax.splitlines()[0]
    links = re.findall(r"\burl='([^']+)'", header)
    if not header.startswith('RootWebArea ') or len(links) != 1:
        raise ValueError('Unique initial document URL required')
    original = urlsplit(links[0])
    if original.scheme not in ('http', 'https') or not original.netloc or original.username or original.password:
        raise ValueError('Initial URL must identify the recorded website')
    path = exact_local_path(local_path(links[0]))
    parsed = urlsplit(path)
    fragment = parse_qs(parsed.fragment, keep_blank_values=True)
    view = initial_view('/#' + parsed.fragment) if 'map' in fragment else None
    query = parse_qs(parsed.query, keep_blank_values=True)
    route = None
    if 'route' in query:
        pair, mode = initial_url_state(path)
        route = {'pair': pair, 'mode': mode}
    fields = {}
    for label in ('From', 'To'):
        lines = [line.strip() for line in ax.splitlines() if re.search(r"\btextbox '" + label + "'(?= |$)", line)]
        if len(lines) > 1:
            raise ValueError('Ambiguous initial route field')
        if lines:
            values = re.findall(r"\bvalue='([^']*)'", lines[0])
            if len(values) > 1:
                raise ValueError('Ambiguous route field value')
            fields[label] = values[0] if values else ''
    return {'start_path': path, 'initial_ax_sha256': hashlib.sha256(ax.encode()).hexdigest(),
            'explicit_view': None if view is None else dict(zip(('zoom', 'latitude', 'longitude'), view)),
            'explicit_route': route, 'route_fields': fields,
            'reference_derived_from_actor_actions': False, 'native_admitted': False}


def from_locator(locator, *, task_id, goal):
    offset, length = locator.get('byte_offset'), locator.get('byte_length')
    if type(offset) is not int or offset < 0 or type(length) is not int or not 0 < length <= 8 * 1024 * 1024:
        raise ValueError('Finite exact source record locator required')
    with Path(locator['source_file']).open('rb') as stream:
        stream.seek(offset)
        raw = stream.read(length)
    if hashlib.sha256(raw).hexdigest() != locator.get('line_sha256'):
        raise ValueError('Source record bytes differ')
    trace = json.loads(raw)
    if trace.get('trace_id') != locator.get('trace_id'):
        raise ValueError('Source trace identity differs')
    result = context(trace, task_id=task_id, goal=goal)
    if result['start_path'] != locator.get('initial_path') or result['initial_ax_sha256'] != locator.get('initial_observation_sha256'):
        raise ValueError('Previously recorded initial observation identity differs')
    return result

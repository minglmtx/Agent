"""Private completion-time oracle for explicitly scoped GitLab derived queries.

This module does not confer admission or assume that a listing's updated_at is
its completion time. Native UI observability and control validation remain
required before registering a task with the ordinary actor runner.
"""
from datetime import datetime, timezone
import re
from .site_database import select_rows

VERSION = 'gitlab-terminal-merge-request-time-v2'
STATE_IDS = {'closed': 2, 'merged': 3}


def build_candidate(source, proposal, native_project):
    """Bind an explicit training derivative; this does not grant admission."""
    from copy import deepcopy
    from .source_revision_binding import binding, exact_local_path, local_path
    if (source.get('domain') != 'gitlab' or source.get('split') != 'train'
            or source.get('heldout_id_goal_trace_overlap') is not False
            or source.get('start_verified_from_original_observation') is not True
            or proposal.get('split') != 'train' or proposal.get('kind') != 'completion_time'
            or proposal.get('derivation_disclosed') is not True
            or proposal.get('source_task_id') != source.get('source_task_id')
            or proposal.get('original_goal') != source.get('original_goal')):
        raise ValueError('Reviewed training-only source and explicit completion proposal required')
    traces = source.get('source_traces')
    if (not isinstance(traces, list) or not traces
            or traces != proposal.get('source_trace_locators')
            or len({t['trace_id'] for t in traces}) != len(traces)
            or any(not re.fullmatch('[0-9a-f]{64}', t.get('line_sha256', '')) for t in traces)):
        raise ValueError('Exact original trajectory provenance required')
    urls = [t['initial_document_url'] for t in traces]
    paths = [local_path(u) for u in urls]
    start = exact_local_path(proposal['start_path'])
    if (paths != [t['initial_path'] for t in traces]
            or list(dict.fromkeys(paths)) != source.get('original_start_paths')
            or start != source.get('proposed_canonical_start') or start != paths[0]):
        raise ValueError('Preserve the reviewed original start and all source starts')
    project = proposal['project_path']
    if native_project.get('path') != project:
        raise ValueError('Native project differs from the public task')
    public_spec = ('family', 'completion_states', 'precision', 'timezone', 'fields', 'empty_answer')
    q = {k: deepcopy(proposal['query'][k]) for k in public_spec}
    q.update(project_id=native_project['id'], project_path=project)
    validate(q)
    page = '/' + project + '/-/merge_requests?scope=all&state=all'
    if proposal.get('page_path') != page:
        raise ValueError('Public reference collection must include all declared terminal states')
    q['reference_path'] = page
    goal = proposal['public_goal']
    if (not isinstance(proposal.get('candidate_task_id'), str) or not proposal['candidate_task_id']
            or proposal['candidate_task_id'] == source['source_task_id']
            or goal == source['original_goal']):
        raise ValueError('Explicitly changed scope requires a distinct derivative identity')
    result = dict(source_task_id=source['source_task_id'], task_id=proposal['candidate_task_id'],
        domain='gitlab', split='train', heldout_quarantine=False,
        original_goal=source['original_goal'], goal=goal, start_path=start,
        recorded_start_urls=urls, recorded_start_paths=paths,
        source_trace_ids=[t['trace_id'] for t in traces], task_text_changed=True,
        goal_revision=dict(version=proposal['version'], original_goal=source['original_goal'],
            derived_goal=goal, reason=proposal['derivation_reason'], equivalent_to_original_goal=False),
        start_revision=None, original_benchmark_equivalence=False, query=q,
        definition_status='candidate_requires_native_query_controls',
        training_admitted=False, native_controls_passed=False, actor_attempts=0)
    binding(result)
    return result


def validate(q):
    if (q.get('family') != 'gitlab_merge_request_completion_time'
            or type(q.get('project_id')) is not int or q['project_id'] <= 0
            or not isinstance(q.get('project_path'), str)
            or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+', q['project_path'])
            or q.get('completion_states') != ['closed', 'merged']
            or q.get('precision') != 'minute' or q.get('timezone') != 'UTC'
            or q.get('fields') != {'completed_at': 'string'}
            or q.get('empty_answer') != 'none'):
        raise ValueError('Explicit project, closed/merged scope, UTC minute and empty-result protocol required')


def timestamp(value):
    if not isinstance(value, str) or not re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}', value):
        raise ValueError('Missing native completion timestamp')
    try:
        actual = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('Invalid native completion timestamp') from error
    # The pinned GitLab PostgreSQL schema stores native timestamps in UTC.
    if actual.tzinfo is None:
        actual = actual.replace(tzinfo=timezone.utc)
    return actual.astimezone(timezone.utc)


def from_rows(q, project, rows, *, expected_count):
    validate(q)
    if project != {'id': q['project_id'], 'path': q['project_path']}:
        raise ValueError('Native project identity differs')
    if type(expected_count) is not int or expected_count < 0 or not isinstance(rows, list) or len(rows) != expected_count:
        raise ValueError('Incomplete native completion collection')
    seen = set(); completion = []
    for row in rows:
        if (type(row.get('id')) is not int or row['id'] <= 0 or row['id'] in seen
                or type(row.get('iid')) is not int or row['iid'] <= 0
                or type(row.get('project_id')) is not int or row['project_id'] != q['project_id']
                or type(row.get('state_id')) is not int or row['state_id'] not in STATE_IDS.values()):
            raise ValueError('Wrong, duplicate or nonterminal native merge request')
        seen.add(row['id'])
        field = 'latest_closed_at' if row['state_id'] == STATE_IDS['closed'] else 'merged_at'
        actual = timestamp(row.get(field))
        completion.append((actual, row['id'], row['iid'], field))
    last = max((r[0] for r in completion), default=None)
    value = 'none' if last is None else last.strftime('%Y-%m-%dT%H:%MZ')
    return {'object_id': 'gitlab-mr-completion:' + str(q['project_id']),
            'values': {'completed_at': value}, 'collection_count': expected_count,
            'project': dict(project), 'source_state': rows,
            'latest_records': [{'id': ident, 'iid': iid, 'timestamp_field': field}
                               for when, ident, iid, field in completion if when == last],
            'scope_version': VERSION}


def reference(site, q):
    """Read a complete project-scoped collection; refuse missing native schema."""
    validate(q)
    projects = select_rows(site, "SELECT p.id,r.path FROM projects p JOIN routes r "
                           "ON r.source_id=p.id AND r.source_type='Project' WHERE p.id=" + str(q['project_id']))
    if len(projects) != 1 or projects[0] != {'id': q['project_id'], 'path': q['project_path']}:
        raise ValueError('Native project identity differs')
    columns = select_rows(site, "SELECT column_name FROM information_schema.columns "
                          "WHERE table_schema='public' AND table_name='merge_request_metrics'")
    if not {'merge_request_id', 'latest_closed_at', 'merged_at'} <= {r['column_name'] for r in columns}:
        raise ValueError('Native merge-request metric timestamp capability missing')
    where = ' WHERE m.target_project_id=' + str(q['project_id']) + ' AND m.state_id IN (2,3)'
    def count():
        result = select_rows(site, 'SELECT COUNT(*) AS n FROM merge_requests m' + where)
        if len(result) != 1 or type(result[0].get('n')) is not int or result[0]['n'] < 0:
            raise ValueError('Complete native collection count unavailable')
        return result[0]['n']
    before = count()
    rows = select_rows(site, 'SELECT m.id,m.iid,m.target_project_id AS project_id,m.state_id,'
                       'x.latest_closed_at,x.merged_at FROM merge_requests m LEFT JOIN merge_request_metrics x '
                       'ON x.merge_request_id=m.id' + where + ' ORDER BY m.id')
    if count() != before:
        raise ValueError('Native completion collection changed during capture')
    return from_rows(q, projects[0], rows, expected_count=before)

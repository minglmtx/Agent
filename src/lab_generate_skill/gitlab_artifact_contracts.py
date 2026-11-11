"""Compile reviewed source definitions for native artifact driver preparation.

This supplies no admission proof. An unchanged source start stays unchanged;
task scope and required fetch counts are explicit rather than borrowed from a
different already-admitted calendar/clone task.
"""
from copy import deepcopy
import re

from .source_revision_binding import binding, exact_local_path, local_path, require_source_binding


def build_candidate(source, proposal, *, inventory):
    if (source.get('domain') != 'gitlab' or source.get('split') != 'train'
            or source.get('heldout_id_goal_trace_overlap') is not False
            or source.get('start_verified_from_original_observation') is not True
            or proposal.get('split') != 'train'
            or proposal.get('derivation_disclosed') is not True
            or proposal.get('source_task_id') != source.get('source_task_id')
            or proposal.get('original_goal') != source.get('original_goal')):
        raise ValueError('Reviewed training-only source and explicit proposal required')
    traces = source.get('source_traces')
    if (not isinstance(traces, list) or not traces
            or proposal.get('source_trace_locators') != traces
            or len({t['trace_id'] for t in traces}) != len(traces)):
        raise ValueError('Exact source trajectory provenance required')
    urls = [t['initial_document_url'] for t in traces]
    paths = [local_path(url) for url in urls]
    if (list(dict.fromkeys(paths)) != source.get('original_start_paths')
            or paths != [t['initial_path'] for t in traces]
            or any(not re.fullmatch('[0-9a-f]{64}', t.get('line_sha256', '')) for t in traces)):
        raise ValueError('Recorded source starts/provenance differ')
    start = exact_local_path(proposal['start_path'])
    if start != source['proposed_canonical_start'] or start != paths[0]:
        raise ValueError('This preparation preserves the reviewed original start')
    # Trajectory order is not the authoritative task-inventory order. Multiple
    # trajectories may share a start; keep their IDs while retaining the
    # inventory's exact URL list and explicitly declaring an alternative start.
    authoritative_urls = inventory.get('recorded_start_urls')
    trace_ids = [t['trace_id'] for t in traces]
    if (inventory.get('task_id') != source['source_task_id']
            or inventory.get('domain') != 'gitlab'
            or inventory.get('goal') != source['original_goal']
            or inventory.get('heldout_quarantine') is not False
            or inventory.get('source_trace_ids') != trace_ids
            or not isinstance(authoritative_urls, list) or not authoritative_urls
            or set(authoritative_urls) != set(urls)):
        raise ValueError('Authoritative task inventory and source observations differ')
    urls = list(authoritative_urls)
    paths = list(map(local_path, urls))
    start_revision = None
    if start != paths[0]:
        start_revision = dict(version='recorded-alternative-start-v1',
            original_start=paths[0], derived_start=start,
            reason='Explicitly select the alternate start already present in source observations; preserve authoritative original start ordering and all original trace IDs.',
            equivalent_to_original_start=False)
    goal = proposal.get('public_goal')
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError('Explicit public goal required')
    project = proposal.get('project_path')
    if project is not None and not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+', project):
        raise ValueError('Invalid public project')
    kind = proposal.get('kind')
    if kind == 'clone':
        if project is None:
            raise ValueError('Clone requires the declared repository')
        params = {'project': project, 'client': 'attempt_local_git_workspace'}
    elif kind in ('atom', 'calendar'):
        count = proposal.get('required_successful_fetches')
        if type(count) is not int or count < 1:
            raise ValueError('Declared positive fetch count required')
        filters = proposal.get('feed_filters')
        path = proposal.get('feed_path')
        if kind == 'calendar':
            if (project is not None or path != '/dashboard/issues.ics'
                    or filters != {'state':['opened'], 'assignee_username':['{authenticated_username}'],
                                   'due_date':['next_month_and_previous_two_weeks']}):
                raise ValueError('Explicit current-user upcoming open-issue calendar scope required')
            params = {'scope': 'current_account_assigned_open_issues',
                      'collection': 'issues', 'due_date_window': 'next_month_and_previous_two_weeks'}
        else:
            if project is None or filters != {'state':['opened']}:
                raise ValueError('Explicit open project collection required')
            if path == '/' + project + '/-/issues.atom':
                collection = 'issues'
            elif path == '/' + project + '/-/merge_requests.atom':
                collection = 'merge_requests'
            else:
                raise ValueError('Feed does not identify the declared collection')
            params = {'scope':'project_open_collection', 'project':project, 'collection':collection}
        params.update(kind=kind, client='attempt_local_persisted_subscription', state='opened',
                      required_successful_fetches=count)
    else:
        raise ValueError('Unsupported native artifact kind')
    changed = goal != source['original_goal']
    result = {
        'source_task_id':source['source_task_id'], 'task_id':proposal['candidate_task_id'],
        'domain':'gitlab', 'split':'train', 'heldout_quarantine':False,
        'original_goal':source['original_goal'], 'goal':goal, 'start_path':start,
        'recorded_start_urls':urls, 'recorded_start_paths':paths,
        'source_trace_ids':trace_ids,
        'task_text_changed':changed,
        'goal_revision':({'version':proposal['version'], 'original_goal':source['original_goal'],
                          'derived_goal':goal, 'reason':'Declare deterministic local artifact completion and original object scope.',
                          'equivalent_to_original_goal':False} if changed else None),
        'start_revision':start_revision, 'original_benchmark_equivalence':False,
        'family':'gitlab_local_artifact.' + kind, 'public_parameters':params,
        'public_task_input':{'goal':goal, 'public_parameters':deepcopy(params),
                             'required_unresolved_public_parameters':[]},
        'definition_status':'candidate_requires_native_driver_validation',
        'training_admitted':False, 'native_controls_passed':False, 'actor_attempts':0,
    }
    binding(result)
    require_source_binding(result, result, inventory, domain='gitlab')
    return deepcopy(result)

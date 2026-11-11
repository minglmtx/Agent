"""Terminal persisted-state checks for explicit local GitLab training tasks.

No UI click, success toast, generated answer, or hidden execution recipe is
accepted as proof. Collectors supply native database rows / complete Git trees.
The initial binding and native guards are private; feedback names conditions.
"""
import re

VERSION = 'gitlab-persisted-mutation-v1'
KINDS = {'profile_name', 'visibility', 'notifications', 'repository_file'}


def _index(rows):
    if not isinstance(rows, list) or any(not isinstance(r, dict) or 'id' not in r for r in rows):
        raise ValueError('Complete native rows required')
    values = {r['id']: r for r in rows}
    if len(values) != len(rows):
        raise ValueError('Duplicate native identities')
    return values


def evaluate(spec, initial, final, *, protected_state_unchanged, runtime_error=None):
    def unknown(reason):
        return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}, 'reason': reason}
    if runtime_error:
        return unknown('Native state capture or execution failed')
    kind = spec.get('kind')
    if kind not in KINDS:
        raise ValueError('Explicit supported mutation contract required')
    if type(protected_state_unchanged) is not bool:
        return unknown('Missing protected-state comparison')
    checks = {'unrelated_state_unchanged': protected_state_unchanged}
    try:
        if initial['identity'] != spec['identity'] or final['identity'] != spec['identity']:
            return unknown('Collector identity differs from bound initial object')
        if kind == 'repository_file':
            path = spec['path']
            if (not isinstance(path, str) or path.startswith('/') or
                    any(p in ('', '.', '..') for p in path.split('/'))):
                raise ValueError('Explicit relative repository path required')
            if not re.fullmatch('[0-9a-f]{64}', spec['content_sha256']):
                raise ValueError('Expected file digest required')
            for value in (initial, final):
                if (not isinstance(value['files'], dict) or not isinstance(value['refs'], dict) or
                        not isinstance(value['head'], str) or not re.fullmatch('[0-9a-f]{40,64}', value['head'])):
                    raise ValueError('Complete native repository snapshot required')
                if value['refs'].get('refs/heads/' + value['branch']) != value['head']:
                    raise ValueError('Native HEAD and branch disagree')
            if initial['branch'] != spec['branch'] or final['branch'] != spec['branch']:
                return unknown('Repository default branch changed')
            if spec['operation'] not in ('create', 'replace'):
                raise ValueError('Explicit create/replace operation required')
            if (path in initial['files']) != (spec['operation'] == 'replace'):
                return unknown('File precondition does not match initial repository')
            if initial.get('content_sha256') == spec['content_sha256']:
                return unknown('Requested file is already satisfied at initialization')
            after = final['files'].get(path)
            if after is not None and (not isinstance(after, dict) or set(after) != {'mode', 'oid'}):
                raise ValueError('Malformed target Git entry')
            checks.update(
                content_committed=bool(after) and after['mode'] == '100644' and final.get('content_sha256') == spec['content_sha256'],
                commit_created=final['head'] != initial['head'],
                initial_commit_is_ancestor=final.get('initial_head_is_ancestor') is True,
                other_files_unchanged={k:v for k,v in initial['files'].items() if k != path} ==
                    {k:v for k,v in final['files'].items() if k != path},
                other_refs_unchanged={k:v for k,v in initial['refs'].items() if k != 'refs/heads/' + spec['branch']} ==
                    {k:v for k,v in final['refs'].items() if k != 'refs/heads/' + spec['branch']})
        else:
            before, after = _index(initial['rows']), _index(final['rows'])
            target = spec['identity']
            old, new = before.get(target), after.get(target)
            if old is None:
                return unknown('Bound initial database row is absent')
            if kind == 'profile_name': field = 'name'
            elif kind == 'visibility': field = 'visibility_level'
            else: field = 'level'
            if field not in old:
                return unknown('Requested native field is absent')
            if old[field] == spec['value']:
                return unknown('Requested value already holds at initialization')
            checks.update(target_value_saved=new is not None and new.get(field) == spec['value'],
                other_rows_unchanged={k:v for k,v in before.items() if k != target} ==
                    {k:v for k,v in after.items() if k != target},
                other_target_fields_unchanged=new is not None and
                    {k:v for k,v in old.items() if k != field} == {k:v for k,v in new.items() if k != field})
    except (KeyError, TypeError, ValueError):
        return unknown('Native mutation evidence is incomplete or inconsistent')
    passed = all(checks.values())
    return {'version': VERSION, 'status': 'success' if passed else 'failure', 'reward': float(passed),
            'checks': checks, 'reason': None}


def feedback(result):
    return {'status': result['status'], 'reward': result['reward'], 'reason': result.get('reason'),
            'checks': [{'name': name, 'passed': passed} for name, passed in result['checks'].items()],
            'reference_values_provided': False, 'action_sequence_provided': False}

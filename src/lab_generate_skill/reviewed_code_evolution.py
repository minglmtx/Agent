"""Exact, source-scoped reuse of reviewed evidence with current Python code.

This does not edit historical pins or import old code. The registry supplies a
pinned offline review and its selected sources; only listed Python code changes
can be accepted. Task definitions, artifacts and ordinary evidence remain exact.
"""
from pathlib import Path
import hashlib
import json


def _read(owner, pin):
    # Import lazily: ProviderReviewCatalog also uses this module for its read.
    from .provider_review_catalog import identity
    path = Path(pin['path'])
    if not path.is_absolute():
        raise ValueError('Absolute code-evolution evidence required')
    before = identity(path); raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin['sha256'] or identity(path) != before:
        raise ValueError('Code-evolution evidence changed')
    owner.files[path] = before
    return json.loads(raw)


def scope(owner):
    config = owner.config.get('_code_evolution')
    if config is None:
        return None
    selected = config['source_ids']
    if not selected or len(selected) != len(set(selected)):
        raise ValueError('Distinct code-evolution sources required')
    review = _read(owner, config['review'])
    original = _read(owner, config['registry'])
    matches = [entry for entry in original['entries']
               if set(selected) <= set(entry['source_ids'])]
    if len(matches) != 1:
        raise ValueError('Code-evolution scope is outside one original registry entry')
    # A code review belongs to the actual proof/configuration it reviewed. A
    # same-ID source in another environment must not borrow its exceptions.
    original_proof = _read(owner, matches[0]['proof_config'])
    active_proof = {k: v for k, v in owner.config.items() if k not in ('_code_evolution', '_evidence_snapshots')}
    if original_proof != active_proof:
        raise ValueError('Code-evolution review belongs to a different proof configuration')
    rows = [r for r in review['rows'] if r['registry'] == config['registry']['path']]
    if (not rows or any(set(r['source_ids']) != set(selected) for r in rows)
            or any(r.get('remaining_ast_identical') is not True for r in rows)
            or any(s not in review['candidate_sha256'] for s in selected)):
        raise ValueError('Exact reviewed code/source scope required')
    return config, review, rows


def accepts(owner, pin, path, actual, *, json_value):
    config = owner.config.get('_code_evolution')
    if config is None or json_value:
        return False
    try:
        rel = path.relative_to(Path(config['project'])).as_posix()
    except ValueError:
        return False
    if not rel.endswith('.py') or not rel.startswith(('src/lab_generate_skill/', 'scripts/')):
        return False
    _, _, rows = scope(owner)
    matches = [r for r in rows if r['path'] == rel and r['old_sha256'] == pin['sha256']
               and r['current_sha256'] == actual]
    return len(matches) == 1


def require_source(owner, sid):
    value = scope(owner)
    if value is None:
        return
    config, review, _ = value
    if sid not in config['source_ids']:
        raise ValueError('Source outside reviewed code evolution')
    candidate = owner.sources[sid]['candidate']
    actual = hashlib.sha256(json.dumps(candidate, sort_keys=True,
                                      separators=(',', ':')).encode()).hexdigest()
    if actual != review['candidate_sha256'][sid]:
        raise ValueError('Source definition changed since code-scope review')


def runtime_dependencies(owner, tested, required):
    """Bind reviewed additions without rewriting the original tested manifest.

    A new helper must have an exact source-scoped review and a reviewed caller.
    Existing members remain subject to their original byte/code-scope checks.
    """
    result = dict(tested)
    missing = set(required) - set(result)
    if set(result) - set(required):
        raise ValueError('Unexpected tested runtime dependencies')
    if not missing:
        return result
    scoped = scope(owner)
    if scoped is None:
        raise ValueError('Added runtime dependencies require explicit review')
    config, review, rows = scoped
    additions = [r for r in review.get('added_runtime_dependencies', [])
                 if r['registry'] == config['registry']['path']]
    if (len(additions) != len(missing)
            or {r['path'] for r in additions} != missing):
        raise ValueError('Exact reviewed dependency additions required')
    for addition in additions:
        name = addition['path']
        caller = addition['reviewed_caller']
        if (set(addition['source_ids']) != set(config['source_ids'])
                or not name.startswith('src/lab_generate_skill/')
                or not name.endswith('.py') or '..' in Path(name).parts
                or len([r for r in rows if r['path'] == caller['path']
                        and r['current_sha256'] == caller['sha256']]) != 1):
            raise ValueError('Added dependency has no exact reviewed caller/source')
        validation = _read(owner, addition['validation'])
        if (validation.get('passed') is not True
                or validation.get('source_ids') != config['source_ids']
                or validation.get('dependency') != dict(path=name, sha256=addition['sha256'])
                or validation.get('reviewed_caller') != caller):
            raise ValueError('Added dependency validation differs')
        result[name] = addition['sha256']
    return result

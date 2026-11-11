"""Select current built-in or reviewed protocols before actor allocation work.

Selection is not admission: the existing bundle validator/runner still checks
claims and source proofs. Recovery stays in the no-inference archive entry.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path


def pinned_json(path, expected):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('Regular absolute runtime configuration required')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Current runtime configuration changed')
    return json.loads(raw)


def frozen_config(project):
    """Read the config shipped with this allocation, never the live workspace."""
    project = Path(project).resolve()
    declaration = project / '.lab-reviewed-frozen-runtime-file-sha256.json'
    if declaration.is_symlink() or not declaration.is_file():
        raise ValueError('Verified frozen runtime required for the current actor entry')
    pins = json.loads(declaration.read_text())
    for name in ('configs/site-runtime-current.json',
                 'src/lab_generate_skill/current_actor_entry.py',
                 'scripts/run_current_site_actor.py'):
        path = project / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != pins.get(name):
            raise ValueError('Unpinned or changed frozen actor entry: ' + name)
    return json.loads((project / 'configs/site-runtime-current.json').read_text())


def map_registry_source_ids(registry):
    sources = [s for entry in registry.get('entries', []) for s in entry['source_ids']]
    retained = registry.get('retained_native_sources')
    if retained is not None:
        sources.extend(retained['source_ids'])
    if (not sources or any(not isinstance(s,str)or not s for s in sources)
            or len(set(sources)) != len(sources)):
        raise ValueError('Distinct current Map registry sources required')
    return set(sources)


def registry_selection(contracts, config):
    """Return a pinned registry only for a wholly registered worker manifest."""
    if not contracts:
        raise ValueError('Nonempty worker contracts required')
    sources = [c.get('source_task_id', c.get('task_id')) for c in contracts]
    if any(not isinstance(s, str) or not s for s in sources) or len(set(sources)) != len(sources):
        raise ValueError('Distinct source identities required')
    pin = config.get('reviewed_map_registry')
    if pin is None:
        return None
    registry = pinned_json(pin['path'], pin['sha256'])
    if registry.get('version') != 'reviewed-map-registry-v1':
        raise ValueError('Unsupported current reviewed registry')
    registered = map_registry_source_ids(registry)
    if len(set(registered)) != len(registered):
        raise ValueError('Duplicate current registry source')
    selected = set(sources) & set(registered)
    if not selected:
        return None
    if selected != set(sources) or any(c.get('domain') != 'map' for c in contracts):
        raise ValueError('Partition ordinary and reviewed startup profiles before execution')
    return dict(pin)


def media_registry_selection(contracts, config):
    pin = config.get('reviewed_media_registry')
    if pin is None:
        return None
    data = pinned_json(pin['path'], pin['sha256'])
    if data.get('version') != 'reviewed-native-media-registry-v1':
        raise ValueError('Unsupported current media registry')
    registered = [r['source_task_id'] for r in data['sources']]
    if not registered or len(set(registered)) != len(registered):
        raise ValueError('Distinct registered media sources required')
    sources = [c.get('source_task_id', c.get('task_id')) for c in contracts]
    if not contracts or any(not isinstance(s, str) or not s for s in sources) or len(set(sources)) != len(sources):
        raise ValueError('Distinct worker sources required')
    selected = set(sources) & set(registered)
    if not selected:
        return None
    if selected != set(sources) or any(c.get('domain') != 'reddit' for c in contracts):
        raise ValueError('Partition ordinary and native media profiles before execution')
    return dict(pin)


def gitlab_registry_selection(contracts, config):
    pin=config.get('reviewed_gitlab_registry')
    if pin is None:return None
    data=pinned_json(pin['path'],pin['sha256'])
    if data.get('version')!='reviewed-original-gitlab-registry-v1':
        raise ValueError('Unsupported current native GitLab registry')
    registered=[r['source_task_id'] for r in data['sources']]
    sources=[c.get('source_task_id',c.get('task_id')) for c in contracts]
    if (not registered or len(set(registered))!=len(registered) or not sources
            or any(not isinstance(s,str)or not s for s in sources)or len(set(sources))!=len(sources)):
        raise ValueError('Distinct registered and worker sources required')
    selected=set(sources)&set(registered)
    if not selected:return None
    if selected!=set(sources)or any(c.get('domain')!='gitlab' for c in contracts):
        raise ValueError('Partition original native GitLab and ordinary profiles before execution')
    return dict(pin)


def remaining_registry_selection(contracts, config):
    pin=config.get('reviewed_remaining_registry')
    if pin is None:return None
    data=pinned_json(pin['path'],pin['sha256'])
    if data.get('version')!='reviewed-native-remaining-registry-v1':
        raise ValueError('Unsupported current native artifact GitLab registry')
    registered=[r['source_task_id'] for r in data['sources']]
    sources=[c.get('source_task_id',c.get('task_id')) for c in contracts]
    if (not registered or len(set(registered))!=len(registered) or not sources
            or any(not isinstance(s,str)or not s for s in sources)or len(set(sources))!=len(sources)):
        raise ValueError('Distinct registered and worker sources required')
    selected=set(sources)&set(registered)
    if not selected:return None
    if selected!=set(sources)or any(c.get('domain')!='gitlab' for c in contracts):
        raise ValueError('Partition original native artifact GitLab and ordinary profiles before execution')
    return dict(pin)

def next_registry_selection(contracts, config):
    pin=config.get('reviewed_next_registry')
    if pin is None:return None
    data=pinned_json(pin['path'],pin['sha256'])
    if data.get('version')!='reviewed-native-next-registry-v1':
        raise ValueError('Unsupported current native artifact GitLab registry')
    registered=[r['source_task_id'] for r in data['sources']]
    sources=[c.get('source_task_id',c.get('task_id')) for c in contracts]
    if (not registered or len(set(registered))!=len(registered) or not sources
            or any(not isinstance(s,str)or not s for s in sources)or len(set(sources))!=len(sources)):
        raise ValueError('Distinct registered and worker sources required')
    selected=set(sources)&set(registered)
    if not selected:return None
    if selected!=set(sources)or any(c.get('domain')!='gitlab' for c in contracts):
        raise ValueError('Partition original native artifact GitLab and ordinary profiles before execution')
    return dict(pin)

def artifact_registry_selection(contracts, config):
    pin=config.get('reviewed_artifact_registry')
    if pin is None:return None
    data=pinned_json(pin['path'],pin['sha256'])
    if data.get('version')!='reviewed-native-artifact-registry-v1':
        raise ValueError('Unsupported current native artifact GitLab registry')
    registered=[r['source_task_id'] for r in data['sources']]
    sources=[c.get('source_task_id',c.get('task_id')) for c in contracts]
    if (not registered or len(set(registered))!=len(registered) or not sources
            or any(not isinstance(s,str)or not s for s in sources)or len(set(sources))!=len(sources)):
        raise ValueError('Distinct registered and worker sources required')
    selected=set(sources)&set(registered)
    if not selected:return None
    if selected!=set(sources)or any(c.get('domain')!='gitlab' for c in contracts):
        raise ValueError('Partition original native artifact GitLab and ordinary profiles before execution')
    return dict(pin)


def reddit_registry_selection(contracts, config):
    pin = config.get('reviewed_reddit_registry')
    if pin is None:
        return None
    data = pinned_json(pin['path'], pin['sha256'])
    if data.get('version') != 'reviewed-original-reddit-registry-v1':
        raise ValueError('Unsupported current native Reddit registry')
    registered = [row['source_task_id'] for row in data['sources']]
    sources = [c.get('source_task_id', c.get('task_id')) for c in contracts]
    if (not registered or len(set(registered)) != len(registered) or not sources
            or any(not isinstance(s, str) or not s for s in sources)
            or len(set(sources)) != len(sources)):
        raise ValueError('Distinct registered and worker Reddit sources required')
    selected = set(sources) & set(registered)
    if not selected:
        return None
    if selected != set(sources) or any(c.get('domain') != 'reddit' for c in contracts):
        raise ValueError('Partition reviewed native Reddit and ordinary profiles')
    return dict(pin)


def retained_topic_selection(contracts,config):
    ref=config.get('retained_topic_registry')
    if ref is None:return None
    registry=pinned_json(ref['path'],ref['sha256'])
    if registry.get('version')!='current-retained-topic-registry-v1':raise ValueError('Unknown retained Topic registry')
    declared={row['source_task_id']:row['contract']for row in registry['sources']}
    if set(declared)!={'1af77c6d697fa92372fe','d2358c64e425307b24c9'}or len(registry['sources'])!=2:raise ValueError('Exact retained Topic source pair required')
    selected=[c.get('source_task_id',c.get('task_id'))for c in contracts]
    if not set(selected)&declared.keys():return None
    if not selected or len(set(selected))!=len(selected)or not set(selected)<=declared.keys():raise ValueError('Dedicated distinct retained Topic sources required')
    for c in contracts:
        sid=c['source_task_id']
        if {k:v for k,v in c.items()if k!='admission_result'}!=declared[sid]:raise ValueError('Executed Topic contract changed')
    return dict(ref)


def tags_registry_selection(contracts,config):
    ref=config.get('reviewed_tags_registry')
    if ref is None:return None
    registry=pinned_json(ref['path'],ref['sha256'])
    if registry.get('version')!='current-tags-subscription-registry-v1':raise ValueError('Unknown Tags registry')
    declared=registry['contract']
    if declared.get('source_task_id')!='13a8e735f2d8b42d9a16' or declared.get('domain')!='gitlab':raise ValueError('Exact GitLab Tags source required')
    selected=[c.get('source_task_id',c.get('task_id'))for c in contracts]
    if declared['source_task_id']not in selected:return None
    if len(contracts)!=1 or {k:v for k,v in contracts[0].items()if k!='admission_result'}!=declared:
        raise ValueError('One exact declared Tags contract required')
    return dict(ref)


@contextmanager
def worker_runner(project, contracts, config):
    tags_pin=tags_registry_selection(contracts,config)
    if tags_pin is not None:
        from .current_tags_registry import CurrentTagsRegistry
        with CurrentTagsRegistry(tags_pin,project=project,contracts=contracts) as registry:
            yield registry.runner
        return

    topic_pin=retained_topic_selection(contracts,config)
    if topic_pin is not None:
        from .current_retained_topic_registry import CurrentRetainedTopicRegistry
        with CurrentRetainedTopicRegistry(topic_pin,project=project,contracts=contracts) as registry:
            yield registry.runner
        return

    reddit_pin = reddit_registry_selection(contracts, config)
    if reddit_pin is not None:
        from .reviewed_reddit_registry import ReviewedRedditRegistry
        selected = {c.get('source_task_id', c['task_id']) for c in contracts}
        with ReviewedRedditRegistry(reddit_pin['path'], reddit_pin['sha256'],
                                   project=project, selected_sources=selected) as registry:
            if len(registry.partition(contracts)) != 1:
                raise ValueError('Worker requires one compatible native Reddit profile')
            yield registry.runner
        return
    remaining_pin=remaining_registry_selection(contracts,config)
    if remaining_pin is not None:
        from .reviewed_remaining_registry import ReviewedRemainingRegistry
        selected={c.get('source_task_id',c['task_id']) for c in contracts}
        with ReviewedRemainingRegistry(remaining_pin['path'],remaining_pin['sha256'],project=project,selected_sources=selected) as registry:
            if len(registry.partition(contracts))!=1:raise ValueError('Worker requires one compatible native artifact profile')
            yield registry.runner
        return

    next_pin=next_registry_selection(contracts,config)
    if next_pin is not None:
        from .reviewed_next_registry import ReviewedNextRegistry
        selected={c.get('source_task_id',c['task_id']) for c in contracts}
        with ReviewedNextRegistry(next_pin['path'],next_pin['sha256'],project=project,selected_sources=selected) as registry:
            if len(registry.partition(contracts))!=1:raise ValueError('Worker requires one compatible native artifact profile')
            yield registry.runner
        return

    artifact_pin=artifact_registry_selection(contracts,config)
    if artifact_pin is not None:
        from .reviewed_artifact_registry import ReviewedArtifactRegistry
        selected={c.get('source_task_id',c['task_id']) for c in contracts}
        with ReviewedArtifactRegistry(artifact_pin['path'],artifact_pin['sha256'],project=project,selected_sources=selected) as registry:
            if len(registry.partition(contracts))!=1:raise ValueError('Worker requires one compatible native artifact profile')
            yield registry.runner
        return
    native_pin=gitlab_registry_selection(contracts,config)
    if native_pin is not None:
        from .reviewed_gitlab_registry import ReviewedGitlabRegistry
        selected={c.get('source_task_id',c['task_id']) for c in contracts}
        with ReviewedGitlabRegistry(native_pin['path'],native_pin['sha256'],project=project,selected_sources=selected) as registry:
            if len(registry.partition(contracts))!=1:raise ValueError('Worker requires one compatible native GitLab profile')
            yield registry.runner
        return
    media_pin = media_registry_selection(contracts, config)
    if media_pin is not None:
        from .reviewed_media_registry import ReviewedMediaRegistry
        with ReviewedMediaRegistry(media_pin['path'], media_pin['sha256'], project=project) as registry:
            if len(registry.partition(contracts)) != 1:
                raise ValueError('Worker requires one compatible media profile')
            yield registry.runner
        return
    pin = registry_selection(contracts, config)
    if pin is None:
        yield None
        return
    from .reviewed_map_registry import ReviewedMapRegistry
    with ReviewedMapRegistry(pin['path'], pin['sha256'], project=project,
                             selected_sources={c.get('source_task_id',c['task_id'])for c in contracts}) as registry:
        groups = registry.partition(contracts)
        if len(groups) != 1:
            raise ValueError('Worker requires one compatible reviewed startup profile')
        yield registry.runner


def bundle_contracts(plan):
    rows = []
    for wave in plan['waves']:
        path = Path(wave['manifest'])
        raw = path.read_bytes()
        if path.is_symlink() or hashlib.sha256(raw).hexdigest() != wave['manifest_sha256']:
            raise ValueError('Worker task manifest changed')
        values = [json.loads(line) for line in raw.splitlines() if line.strip()]
        if wave['domain'] != plan['domain'] or any(v.get('domain') != plan['domain'] for v in values):
            raise ValueError('Worker website changed')
        ids = {(v.get('source_task_id', v['task_id']), v['task_id']) for v in values}
        expected = {(v['source_task_id'], v['task_id']) for v in wave['proofs']}
        if len(ids) != len(values) or ids != expected:
            raise ValueError('Worker manifest differs from claimed sources')
        rows.extend(values)
    return rows

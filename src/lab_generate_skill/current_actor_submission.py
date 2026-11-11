"""Prepare claims and launches with the same published code used by workers."""
from contextlib import contextmanager, ExitStack
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from .frozen_actor_capsule import build, extract, sha, regular
from .current_actor_entry import pinned_json, map_registry_source_ids, retained_topic_selection, tags_registry_selection


# Admin's Python runner launches these files through PHP, bash and Python.
# They are executable dependencies, even though they live outside src/scripts.
ADMIN_RUNTIME_RESOURCES = (
    'cluster/admin-pilot-state.php',
    'cluster/admin-database-snapshot.php',
    'cluster/admin-pilot-fixture-v2.php',
    'cluster/admin-mail-sink.php',
    'cluster/start-admin.sh',
    'cluster/stage1_site_bridge.py',
)


class SubmissionRegistries:
    def __init__(self, registries):
        self.registries = registries
        self.sources = {}
        for registry in registries:
            if self.sources.keys() & registry.sources.keys():
                raise ValueError('Duplicate sources across current registries')
            self.sources.update(registry.sources)

    def partition(self, contracts):
        ids = {c.get('source_task_id', c['task_id']) for c in contracts}
        matches = [r for r in self.registries if ids & r.sources.keys()]
        if len(matches) != 1 or not ids <= matches[0].sources.keys():
            raise ValueError('Partition current registered families before claiming')
        return matches[0].partition(contracts)


@contextmanager
def submission_registry(project, specs, config):
    from .reviewed_map_registry import ReviewedMapRegistry
    from .reviewed_media_registry import ReviewedMediaRegistry
    from .reviewed_gitlab_registry import ReviewedGitlabRegistry
    from .reviewed_artifact_registry import ReviewedArtifactRegistry
    from .reviewed_next_registry import ReviewedNextRegistry
    from .reviewed_remaining_registry import ReviewedRemainingRegistry
    from .reviewed_reddit_registry import ReviewedRedditRegistry
    selected = {row.get('source_task_id', row['task_id']) for spec in specs
                for row in map(json.loads, Path(spec['manifest']).read_text().splitlines())}
    contracts = [json.loads(line) for spec in specs for line in Path(spec['manifest']).read_text().splitlines() if line.strip()]
    tags_ref = tags_registry_selection(contracts, config)
    if tags_ref is not None:
        from .current_tags_registry import CurrentTagsRegistry
        with CurrentTagsRegistry(tags_ref, project=project, contracts=contracts) as registry:
            yield SubmissionRegistries([registry])
        return
    topic_ref = retained_topic_selection(contracts, config)
    if topic_ref is not None:
        from .current_retained_topic_registry import CurrentRetainedTopicRegistry
        with CurrentRetainedTopicRegistry(topic_ref, project=project, contracts=contracts) as registry:
            yield SubmissionRegistries([registry])
        return
    with ExitStack() as stack:
        loaded = []
        for key, cls in [('reviewed_map_registry', ReviewedMapRegistry),
                         ('reviewed_media_registry', ReviewedMediaRegistry),
                         ('reviewed_gitlab_registry', ReviewedGitlabRegistry),
                         ('reviewed_artifact_registry', ReviewedArtifactRegistry),
                         ('reviewed_next_registry', ReviewedNextRegistry),
                         ('reviewed_remaining_registry', ReviewedRemainingRegistry),
                         ('reviewed_reddit_registry', ReviewedRedditRegistry)]:
            pin = config.get(key)
            if pin is None:
                continue
            data = pinned_json(pin['path'], pin['sha256'])
            registered = ({r['source_task_id'] for r in data['sources']} if key != 'reviewed_map_registry'
                          else map_registry_source_ids(data))
            if selected & registered:
                kwargs={'project':project}
                if key in ('reviewed_map_registry', 'reviewed_gitlab_registry', 'reviewed_reddit_registry', 'reviewed_artifact_registry', 'reviewed_next_registry', 'reviewed_remaining_registry', 'retained_topic_registry', 'reviewed_tags_registry'):kwargs['selected_sources']=selected
                loaded.append(stack.enter_context(cls(pin['path'],pin['sha256'],**kwargs)))
        yield SubmissionRegistries(loaded) if loaded else None


def freeze_published(project, directory):
    project = Path(project).resolve()
    file = project / 'configs/site-runtime-current.json'
    config_sha = sha(file)
    config = json.loads(file.read_text())
    declaration = config.get('actor_submission', {})
    if declaration.get('version') != 'frozen-current-actor-submission-v1':
        raise ValueError('Current frozen actor submission has not been published')
    members = declaration['files_sha256']
    if not members or 'configs/site-runtime-current.json' in members:
        raise ValueError('Explicit nonrecursive published runtime members required')
    if 'src/lab_generate_skill/admin_pilot.py' in members:
        missing = set(ADMIN_RUNTIME_RESOURCES) - members.keys()
        if missing:
            raise ValueError('Admin runtime resources absent from published capsule: '
                             + ', '.join(sorted(missing)))
    for registry_key in ('reviewed_map_registry', 'reviewed_media_registry', 'reviewed_gitlab_registry', 'reviewed_reddit_registry', 'reviewed_artifact_registry', 'reviewed_next_registry', 'reviewed_remaining_registry', 'retained_topic_registry', 'reviewed_tags_registry'):
        registry_pin = config.get(registry_key)
        if registry_pin is not None:
            registry = pinned_json(registry_pin['path'], registry_pin['sha256'])
            for name, expected in registry.get('runtime_files', {}).items():
                if members.get(name) != expected:
                    raise ValueError('Reviewed task registry dependency differs from actor capsule: ' + name)
    # Executable resources are runtime code too. A publisher must not silently
    # omit PHP/Ruby/etc. while retaining only Python files in the actor capsule.
    for name, expected in config.get('production_files_sha256', {}).items():
        if name.startswith(('src/', 'scripts/', 'cluster/')) and members.get(name) != expected:
            raise ValueError('Published runtime dependency absent or stale in actor capsule: ' + name)
    for name, expected in members.items():
        if sha(regular(project, name)) != expected:
            raise ValueError('Code differs from published runtime: ' + name)
    capsule = build(project, directory, [*members, 'configs/site-runtime-current.json'])
    frozen = json.loads(Path(capsule['path']).read_text())['members']
    expected = {**members, 'configs/site-runtime-current.json': config_sha}
    if {name: value['sha256'] for name, value in frozen.items()} != expected:
        raise ValueError('Publication changed while freezing runtime')
    return capsule


def prepare_current(specs, out, *, project, root, capacity=32, parallel=6, partition='a40'):
    """Freeze once; expand temporarily on local storage for CPU-only admission."""
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(out)
    package = out.with_name(out.name + '-runtime')
    capsule = freeze_published(project, package)
    specs_file = package / 'specs.json'
    specs_file.write_text(json.dumps(specs, sort_keys=True) + '\n')
    with tempfile.TemporaryDirectory(prefix='prepare-current-actor-') as tmp:
        frozen = extract(capsule['path'], capsule['sha256'], Path(tmp) / 'runtime')
        import os
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                   PYTHONPATH=str(frozen/'src') + ':' + str(frozen/'scripts'))
        for key in ('OPENROUTER_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY'):
            env.pop(key, None)
        command = [sys.executable, '-B', str(frozen/'scripts/prepare_frozen_site_batch.py'),
                   '--specs', str(specs_file), '--specs-sha256', sha(specs_file),
                   '--out', str(out), '--root', str(root),
                   '--capsule', capsule['path'], '--capsule-sha256', capsule['sha256'],
                   '--tasks-per-worker', str(capacity), '--parallel', str(parallel),
                   '--partition', partition]
        # Preparation may create exclusive claims. An interruption never retries
        # automatically; the capsule and partial claim manifest remain available.
        subprocess.run(command, env=env, check=True, timeout=600)
    return json.loads((out/'batch-plan.json').read_text())

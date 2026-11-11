"""Opt-in static data adapter via iD's native fileFetcher API; no service mocks."""
import hashlib,json,shutil
from pathlib import Path,PurePosixPath

PREFIX='/local-id-presets-6.0.0/'
REQUIRED={'presets_package':'package.json','deprecated':'dist/deprecated.min.json',
    'discarded':'dist/discarded.min.json','preset_categories':'dist/preset_categories.min.json',
    'preset_defaults':'dist/preset_defaults.min.json','preset_fields':'dist/fields.min.json',
    'preset_presets':'dist/presets.min.json','locales_index_tagging':'dist/translations/index.min.json'}


def checked_assets(directory):
    directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text())
    if manifest.get('package')!='@openstreetmap/id-tagging-schema'or manifest.get('version')!='6.0.0':
        raise ValueError('Pinned upstream editor schema required')
    files=manifest.get('files',{})
    if not (set(REQUIRED.values())|{'dist/translations/en.min.json'})<=set(files):
        raise ValueError('Incomplete editor schema or English translations')
    for rel,spec in files.items():
        p=PurePosixPath(rel)
        if p.is_absolute()or '..'in p.parts:raise ValueError('Unsafe editor asset path')
        file=directory/rel
        if file.is_symlink()or not file.is_file()or not file.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Editor asset must be a local regular file')
        data=file.read_bytes()
        if len(data)!=spec['bytes']or hashlib.sha256(data).hexdigest()!=spec['sha256']:
            raise ValueError('Static editor asset checksum mismatch')
    return manifest


def file_map(manifest):
    mapping={k:PREFIX+v for k,v in REQUIRED.items()}
    for rel in manifest['files']:
        if rel.startswith('dist/translations/')and rel.endswith('.min.json')and Path(rel).name!='index.min.json':
            locale=Path(rel).name[:-len('.min.json')]
            mapping['locale_tagging_'+locale]=PREFIX+rel
    return mapping


def install(site,directory):
    if not site.state.is_relative_to(Path(site.temporary.name)):
        raise ValueError('Editor assets may only be installed in a disposable site')
    manifest=checked_assets(directory);app=site.state/'frontend/app'
    target=app/'public'/PREFIX.strip('/');target.mkdir(exist_ok=False)
    for rel in manifest['files']:
        output=target/rel;output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(Path(directory)/rel,output)
    source=app/'app/assets/javascripts/id.js';text=source.read_text()
    needle='    idContext.connection().apiConnections([]);'
    if text.count(needle)!=1:raise ValueError('Native iD integration changed')
    # Absolute same-origin URLs bypass iD's assetPath prefix. The package and
    # translations stay native; only their transport location is changed.
    patch='''
    var localPresetFiles = MAPPING;
    Object.keys(localPresetFiles).forEach(function(key) {
      localPresetFiles[key] = location.origin + localPresetFiles[key];
    });
    iD.fileFetcher.fileMap(Object.assign({}, iD.fileFetcher.fileMap(), localPresetFiles));
'''.replace('MAPPING',json.dumps(file_map(manifest),sort_keys=True))
    source.write_text(text.replace(needle,needle+patch))
    return {'package':manifest['package'],'version':manifest['version'],
        'manifest_sha256':hashlib.sha256((Path(directory)/'manifest.json').read_bytes()).hexdigest(),
        'native_integration_before_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'native_integration_after_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'static_files':len(manifest['files']),'external_services_mocked':False,'task_admissions':0}

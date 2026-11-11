"""Opt-in native iD custom background using the local snapshot tile renderer.

Uses the bundled editor's supported background/overlays hash parameters. No
fake tile response, changed map records, or task-specific navigation strategy.
"""
import hashlib,json
from pathlib import Path
from urllib.parse import urlsplit


def install(site):
    if not site.state.is_relative_to(Path(site.temporary.name)):
        raise ValueError('Editor tile configuration requires a disposable site')
    url=site.tile_url
    if not isinstance(url,str):raise ValueError('Native local tile service required')
    u=urlsplit(url)
    if u.scheme!='http' or u.hostname!='127.0.0.1' or not u.port or u.path or u.query or u.fragment or u.username or u.password:
        raise ValueError('Only the isolated local tile endpoint is allowed')
    app=site.state/'frontend/app'
    imagery=app/'vendor/assets/iD/iD/data/imagery.min.json'
    records=json.loads(imagery.read_text())
    # Native background.init enables the first default overlay, then toggles
    # any overlays named in the hash. Naming it here turns the external
    # locator off; the local base map already includes those labels.
    defaults=[r['id']for r in records if r.get('overlay')and r.get('default')]
    if not defaults:raise ValueError('Native default overlay is unknown')
    source=app/'app/assets/javascripts/id.js';text=source.read_text()
    needle='    var idContext = iD.coreContext();'
    if text.count(needle)!=1:raise ValueError('Native editor entry point changed')
    template=url+'/tile/{z}/{x}/{y}.png'
    patch='''    var localEditorHash = new URLSearchParams(location.hash.slice(1));
    localEditorHash.set("background", BACKGROUND);
    localEditorHash.set("overlays", OVERLAY);
    history.replaceState(null, "", "#" + localEditorHash.toString());
'''.replace('BACKGROUND',json.dumps('custom:'+template)).replace('OVERLAY',json.dumps(defaults[0]))
    source.write_text(text.replace(needle,patch+needle))
    return {'native_custom_background':True,'tile_template':template,'disabled_default_overlay':defaults[0],
        'imagery_index_sha256':hashlib.sha256(imagery.read_bytes()).hexdigest(),
        'integration_before_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'integration_after_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'external_services_mocked':False,'geographic_records_modified':False}

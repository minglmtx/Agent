"""Private deployment of the original map frontend, search and routing snapshots.

Geographic baselines are opt-in and must be fully published before reuse. Schema
probes may still use an empty app DB, which is never a benchmark reset baseline.
Service readiness alone does not admit benchmark tasks.
"""
import json
import hashlib
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from .admin_ports import PortLease
from .io_utils import atomic_write_json


def remap_routing_ports(source, ports):
    """Change deployment ports only, refusing drift in the pinned native engine."""
    if set(ports) != {'car', 'bike', 'foot'} or len(set(ports.values())) != 3:
        raise ValueError('Three distinct routing ports required')
    for profile, old in zip(('car', 'bike', 'foot'), ('5000', '5001', '5002')):
        port = ports[profile]
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError('Invalid service port')
        needle = '"' + profile + '": "' + old + '"'
        if source.count(needle) != 1:
            raise ValueError('Pinned OSRM engine port mapping changed')
        source = source.replace(needle, '"' + profile + '": "' + str(port) + '"')
    return source


def preserve_shortlink_port(source):
    """Keep native short-code encoding; preserve the isolated server's port.

    The upstream default-host deployment used hostname in its non-osm.org
    fallback, which drops a leased HTTP port. Do not redirect to another host
    or change the code, marker, layer or zoom algorithms.
    """
    old='window.location.protocol + "//" + window.location.hostname + "/go/"'
    new='window.location.protocol + "//" + window.location.host + "/go/"'
    if source.count(old)!=1:
        raise ValueError('Pinned native short-link origin expression changed')
    return source.replace(old,new)


def read_app_baseline(images):
    baseline=Path(images)/'app-baseline'
    metadata=json.loads((baseline/'baseline.json').read_text())
    if metadata.get('status')!='complete' or metadata.get('full_snapshot_imported') is not True:
        raise ValueError('Full geographic baseline has not been published')
    if metadata.get('postgres_version')!='11' or (baseline/'postgres/PG_VERSION').read_text().strip()!='11':
        raise ValueError('Geographic baseline PostgreSQL version mismatch')
    if (baseline/'postgres/postmaster.pid').exists():
        raise ValueError('Geographic baseline is not a clean offline snapshot')
    for kind in ('node','way'):
        check=metadata.get('object_checks',{}).get(kind,{})
        if check.get('http_status')!=200 or not check.get('has_object_id') or not check.get('id'):
            raise ValueError('Geographic baseline lacks native object page validation')
    return metadata


def clear_frontend_transients(app, *, preserve_compiled_assets=False):
    """Drop runtime caches and PIDs; optionally retain Sprockets' compiled assets.

    Compiled JS/CSS contain no database or browser session state. Only the
    same deployment's asset cache may survive; persistent task files and the
    database remain subject to the independent MapResetGuard.
    """
    app=Path(app);cache=app/'tmp/cache'
    if cache.is_symlink():raise ValueError('Unexpected Map cache symlink')
    if preserve_compiled_assets and cache.exists():
        for child in cache.iterdir():
            if child.name=='assets' and child.is_dir() and not child.is_symlink():
                for asset_child in child.iterdir():
                    if asset_child.name=='sprockets' and asset_child.is_dir() and not asset_child.is_symlink():continue
                    if asset_child.is_dir() and not asset_child.is_symlink():shutil.rmtree(asset_child)
                    else:asset_child.unlink()
            elif child.is_dir() and not child.is_symlink():shutil.rmtree(child)
            else:child.unlink()
    else:shutil.rmtree(cache,ignore_errors=True)
    cache.mkdir(parents=True,exist_ok=True)
    pids=app/'tmp/pids'
    if pids.is_symlink():pids.unlink()
    else:shutil.rmtree(pids,ignore_errors=True)
    pids.mkdir(parents=True,exist_ok=True)


def native_web_environment(workers):
    if type(workers)is not int or workers not in (0,2):raise ValueError("Reviewed native Puma worker count required")
    return ["--env", "WEB_CONCURRENCY=" + str(workers)]


class IsolatedMapQuerySite:
    domain = 'map'
    full_runtime_validated = False

    def __init__(self, root, logs, *, with_tiles=False, with_geographic_baseline=False, track_changes=False, export_preload=True, community_fixture=None, native_layer_refresh=False, web_workers=0, native_assets_manifest=None, native_frontend_manifest=None, native_provider_manifest=None, native_share_observer=False, native_short_routes=False):
        if type(native_share_observer)is not bool or (native_share_observer and
                (not (with_tiles and with_geographic_baseline and track_changes) or
                 native_layer_refresh or native_provider_manifest is not None or
                 native_frontend_manifest is not None or community_fixture is not None)):
            raise ValueError('Share observer requires a separate full tracked Map profile')
        self.native_share_observer=native_share_observer
        if type(native_short_routes)is not bool or (native_short_routes and not native_share_observer):
            raise ValueError('Compact routes require the tracked native share profile')
        self.short_routes=native_short_routes
        self.native_provider_manifest=native_provider_manifest
        self.provider_environment=None
        self.native_provider_binding=None
        if native_provider_manifest is not None:
            if not (with_tiles and with_geographic_baseline and track_changes) or native_layer_refresh or native_frontend_manifest is not None or community_fixture is not None:
                raise ValueError('Frozen providers require a separate full tracked Map profile')
            from .map_provider_environment import read_profile
            read_profile(native_provider_manifest)
        self.native_frontend_manifest=native_frontend_manifest
        if native_assets_manifest is not None:
            from .next40_route_assets import native_asset_selection
            self.native_assets=native_asset_selection(native_assets_manifest)
        else:self.native_assets=None
        self.route_datasets=(self.native_assets['route_datasets'] if self.native_assets else {p:'us-northeast-latest.osrm' for p in ('car','bike','foot')})
        self.native_web_env=native_web_environment(web_workers)
        self.web_workers=web_workers
        if type(native_layer_refresh)is not bool:raise ValueError("Explicit native layer startup profile required")
        self.native_layer_refresh=native_layer_refresh
        if community_fixture is not None:
            from .map_community_fixture import SUPPORTED_PROFILES
            if community_fixture not in SUPPORTED_PROFILES or not with_geographic_baseline or not track_changes:
                raise ValueError('Community task profile requires the known version and full geographic/reset tracking')
        self.root, self.logs = Path(root), Path(logs)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.active, self.handles, self.events = [], [], []
        self.named_processes = {}
        self.temporary = self.ports = None
        self.with_tiles = with_tiles
        self.tile_url = None
        self.with_geographic_baseline = with_geographic_baseline
        self.geographic_baseline = None
        self.track_changes = track_changes
        self.export_preload = export_preload
        self.reset_guard = None
        self.community_fixture=community_fixture

    def event(self, name, started, **extra):
        self.events.append({'phase': name, 'seconds': time.monotonic() - started, **extra})
        atomic_write_json(self.logs / 'progress.json', self.events)

    def launch(self, command, name):
        # A reset relaunch must preserve the previous service's diagnostics.
        handle = (self.logs / (name + '.log')).open('a')
        handle.write('\n--- service launch: '+name+' ---\n'); handle.flush()
        self.handles.append(handle)
        process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
        self.active.append(process)
        self.named_processes[name] = process
        return process

    def stop_service(self, name, signal_number=signal.SIGTERM, seconds=30):
        # Only the host process group created by launch is owned here. Never
        # use a postmaster/Puma PID from a container's separate PID namespace.
        process=self.named_processes[name];began=time.monotonic()
        if seconds<=0:raise ValueError('Bounded owned-service stop budget required')
        forced=False;graceful_timeout=False
        try:os.killpg(process.pid,signal_number)
        except ProcessLookupError:pass
        try:process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            graceful_timeout=True;forced=True
            self.event('owned_service_grace_timeout',began,service=name,timeout_seconds=seconds,returncode=process.poll())
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            # A successful forced stop is a reset mechanism, not a failed task.
            # Preserve the first grace timeout and require complete owned-group
            # termination before relaunch. Neither this wait nor cleanup is
            # unbounded; persistent survivors still reject the reset.
            process.wait(timeout=5)
        end=time.monotonic()+5
        while True:
            try:os.killpg(process.pid,0)
            except ProcessLookupError:break
            if not forced:
                forced=True
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            if time.monotonic()>=end:
                self.event('owned_service_stop',began,service=name,graceful_timeout=graceful_timeout,
                    forced_stop=forced,owned_group_fully_stopped=False,returncode=process.poll())
                raise TimeoutError('Owned map service process group did not terminate: '+name)
            time.sleep(min(.05,max(0,end-time.monotonic())))
        self.event('owned_service_stop',began,service=name,graceful_timeout=graceful_timeout,
            forced_stop=forced,owned_group_fully_stopped=True,returncode=process.poll())

    def run(self, command, name, seconds=180):
        started = time.monotonic()
        process = self.launch(command, name)
        try:
            rc = process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise TimeoutError(name + ' exceeded ' + str(seconds) + ' seconds')
        self.event(name, started, returncode=rc)
        if rc:
            raise RuntimeError(name + ' failed; inspect ' + str(self.logs / (name + '.log')))

    def wait_http(self, url, seconds=180, *, request_seconds=10):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=min(request_seconds,max(.01,deadline-time.monotonic()))) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                atomic_write_json(self.logs / 'http-error.json', {
                    'url': url, 'code': exc.code, 'body': exc.read().decode('utf-8', 'replace')[:6000]})
                raise RuntimeError('Map HTTP failure ' + str(exc.code)) from exc
            except (urllib.error.URLError, TimeoutError):
                # active also owns deliberately retired process groups for
                # cleanup. Only the current instance of each service matters.
                if any(p.poll() not in (None, 0) for p in self.named_processes.values()):
                    raise RuntimeError('Map service exited before readiness')
                time.sleep(.5)
        raise TimeoutError('Map HTTP readiness: ' + url)

    def wait_postgres(self, command, username, name):
        from .service_readiness import wait_for_command
        def running():
            return (self.named_processes[name].poll() is None and
                    all(p.poll() in (None, 0) for p in self.named_processes.values()))
        def record(row):
            with (self.logs/(name+'-readiness.jsonl')).open('a') as stream:
                stream.write(json.dumps(row)+'\n')
        return wait_for_command(command + ['-h', '/state/run', '-U', username],
                                service_running=running,poll_interval=.5,record=record)

    def __enter__(self):
        if not os.environ.get('SLURM_JOB_ID') or not os.environ.get('TMPDIR'):
            raise RuntimeError('Compute allocation required')
        try:
            self.temporary = tempfile.TemporaryDirectory(prefix='map-query-site-', dir=os.environ['TMPDIR'])
            self.state = Path(self.temporary.name)
            self.ports = PortLease(count=6 if self.with_tiles else 5)
            webport, searchport = self.ports.ports[:2]
            routeports = self.ports.ports[2:5]
            self.url = 'http://127.0.0.1:' + str(webport)
            self.search_url = 'http://127.0.0.1:' + str(searchport)
            self.route_urls = dict(zip(('car', 'bike', 'foot'), ['http://127.0.0.1:' + str(p) for p in routeports]))
            self.allowed_netlocs = tuple('127.0.0.1:' + str(p) for p in self.ports.ports)
            images = Path(self.native_assets['images_directory']) if self.native_assets else self.root / 'containers/webarena/map'
            for kind in ('nominatim', 'osrm'):
                if not (images / 'query-data' / kind / 'stage.json').exists():
                    raise RuntimeError('Map data stage incomplete: ' + kind)
            self.images = images
            if self.with_geographic_baseline:
                self.geographic_baseline=self.load_geographic_baseline(images)
            for sub in ('search', 'frontend'):
                parent = self.state / sub
                for name in ('run', 'tmp', 'project'):
                    (parent / name).mkdir(parents=True, mode=0o700)
                (parent / 'hosts').write_text('127.0.0.1 localhost ' + socket.gethostname() + '\n::1 localhost\n')
            self.start_search(searchport)
            self.start_routes(routeports)
            if self.with_tiles:
                from .map_tiles import start_native_tiles
                self.tile_url = start_native_tiles(self, self.ports.ports[5])
            self.start_frontend(webport)
            if self.community_fixture is not None:
                from .map_community_fixture import install,records,GPS_PROFILE
                install(self)
                if self.community_fixture==GPS_PROFILE:
                    from .map_gps_fixture import install as install_gps,records as gps_records
                    install_gps(self,stable_keys=True)
                atomic_write_json(self.logs/'community-fixture.json',{'version':self.community_fixture,
                    'synthetic_content':True,'original_benchmark_equivalence':False,'records':records(self),
                    **({'gps_records':gps_records(self)}if self.community_fixture==GPS_PROFILE else {})})
            if self.native_provider_manifest is not None:
                from .map_provider_environment import ProviderEnvironment
                self.provider_environment=ProviderEnvironment(self,self.native_provider_manifest)
                self.native_provider_binding=self.provider_environment.install()
            if self.track_changes:
                if not self.with_geographic_baseline:
                    raise ValueError('Tracked task resets require the full geographic baseline')
                from .map_reset_guard import MapResetGuard
                self.reset_guard = MapResetGuard(self)
            atomic_write_json(self.logs / 'deployment.json', {
                'url': self.url, 'search_url': self.search_url, 'routing': self.route_urls,
                'full_runtime_validated': False, 'empty_app_geographic_database': not self.with_geographic_baseline,
                'geographic_baseline':self.geographic_baseline,
                'tiles_available': bool(self.tile_url), 'original_source_unchanged': self.native_provider_manifest is None,
                'frozen_provider_environment':self.native_provider_binding,
                'community_fixture':self.community_fixture,
                'original_benchmark_equivalence':False if self.community_fixture or self.native_provider_manifest else None,
                'deployment_only_patches': ['private database socket', 'loopback service URLs', 'leased OSRM ports', 'preserve leased frontend port in native short links'],
                'api_calls': 0})
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def flags(self, state):
        return ['apptainer', 'exec', '--cleanenv', '--containall', '--no-home', '--no-mount',
                'bind-paths,hostfs,cwd', '--bind', str(state) + ':/state', '--bind',
                str(state / 'tmp') + ':/tmp', '--bind', str(state / 'hosts') + ':/etc/hosts:ro', '--pwd', '/state']

    def start_search(self, port):
        state = self.state / 'search'
        data = self.images / 'query-data/nominatim/postgres'
        if self.native_assets is not None:
            # The actual native4.2.4 import project contains its tokenizer and
            # website support. Clone all original immutable project files;
            # refresh below then rebinds only the current instance's transport.
            # native_asset_selection has already hashed the full factory.
            from .next40_route_assets import native_asset_selection
            native_asset_selection(self.native_assets['selected_manifest_path'])
            original_project=self.images/'query-data/nominatim/project'
            if original_project.is_symlink()or not original_project.is_dir()or not(original_project/'tokenizer').is_dir():
                raise ValueError('Complete actual native search project/tokenizer missing')
            target_project=state/'project'
            if target_project.is_symlink()or any(target_project.iterdir()):
                raise ValueError('Fresh independent search project required')
            shutil.copytree(original_project,target_project,dirs_exist_ok=True,symlinks=False)
        # Reuse the bounded private-copy path already used for the app database.
        # The 37 GB native search snapshot can exceed the serial NFS copy limit.
        # Each episode still receives its own writable database; the helper
        # rejects aliases and checks the immutable source throughout the copy.
        import sys
        script = Path(__file__).resolve().parents[2] / 'scripts/clone_map_snapshot.py'
        self.run([sys.executable, str(script), '--source', str(data),
                  '--destination', str(state / 'postgres'), '--progress',
                  str(self.logs / 'search-clone-progress.json')], 'clone_search_database', 1800)
        (state / 'postgres').chmod(0o700)
        (state / 'postgres/postmaster.pid').unlink(missing_ok=True)
        (state / 'postgresql.conf').write_text("data_directory='/state/postgres'\nhba_file='/state/pg_hba.conf'\nlisten_addresses=''\nunix_socket_directories='/state/run'\nshared_buffers=512MB\nmax_connections=24\nmax_parallel_workers=2\njit=off\n")
        (state / 'pg_hba.conf').write_text('local all all trust\n')
        base = self.flags(state) + [str(self.images / 'nominatim.sif')]
        self.launch(base + ['/usr/lib/postgresql/14/bin/postgres', '-D', '/state/postgres', '-c', 'config_file=/state/postgresql.conf'], 'search_postgres')
        self.wait_postgres(base + ['/usr/lib/postgresql/14/bin/pg_isready'], 'nominatim', 'search_postgres')
        (state / 'project/.env').write_text('NOMINATIM_DATABASE_DSN="pgsql:dbname=nominatim;host=/state/run;user=nominatim"\nNOMINATIM_DATABASE_WEBUSER="nominatim"\nNOMINATIM_REPLICATION_URL=""\n')
        self.run(base + ['nominatim', 'refresh', '--project-dir', '/state/project', '--website'], 'prepare_search_website')
        (state / 'project/router.php').write_text('''<?php
$path=parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
if (!preg_match('~^/(search|reverse|lookup|details|status|polygons|deletable)(?:\\.php)?/?$~', $path, $m)) {
    http_response_code(404); echo 'Unknown local map endpoint'; return;
}
require '/state/project/website/'.$m[1].'.php';
''')
        self.launch(base + ['php', '-S', '127.0.0.1:' + str(port), '-t', '/state/project/website', '/state/project/router.php'], 'search_http')
        self.wait_http(self.search_url + '/search?q=Pittsburgh&format=jsonv2&limit=1')

    def start_routes(self, ports):
        state = self.state / 'search'
        base = self.flags(state) + ['--bind', str(self.images / 'query-data/osrm') + ':/data:ro', str(self.images / 'osrm.sif')]
        for profile, port in zip(('car', 'bike', 'foot'), ports):
            self.launch(base + ['osrm-routed', '--algorithm', 'mld', '--mmap', '--threads', '1', '--ip', '127.0.0.1', '--port', str(port), '/data/' + profile + '/' + self.route_datasets[profile]], 'route_' + profile)
        for url in self.route_urls.values():
            self.wait_http(url + '/route/v1/driving/-73.9857,40.7484;-73.9654,40.7829?overview=false&steps=false')

    def load_geographic_baseline(self,images):
        return read_app_baseline(images)

    def prepare_app_database(self,state,db):
        if self.with_geographic_baseline:
            if os.environ.get('LAB_MAP_PARALLEL_APP_CLONE', '1')=='1':
                # The full native app snapshot is substantially larger than
                # the tile database. Two independent native app probes verified
                # pages, reset, and source integrity with this bounded copy.
                # Set LAB_MAP_PARALLEL_APP_CLONE=0 for serial-copy diagnosis.
                import sys
                script=Path(__file__).resolve().parents[2]/'scripts/clone_map_snapshot.py'
                self.run([sys.executable,str(script),'--source',str(self.images/'app-baseline/postgres'),
                          '--destination',str(state/'pg'),'--progress',str(self.logs/'app-clone-progress.json')],
                         'clone_app_geographic_database',1800)
            else:
                self.run(['cp','-a','--reflink=auto',str(self.images/'app-baseline/postgres'),str(state/'pg')],'clone_app_geographic_database',1800)
            (state/'pg').chmod(0o700)
        else:
            self.run(db + ['initdb', '-D', '/state/pg', '-U', 'openstreetmap', '--auth-local=trust', '--auth-host=reject', '--encoding=UTF8', '--locale=C.UTF-8'], 'init_app_database')

    def start_frontend(self, port):
        state = self.state / 'frontend'; app = state / 'app'
        started = time.monotonic()
        shutil.copytree(self.root / 'datasets/webarena-map-frontend/openstreetmap-website', app,
                        ignore=shutil.ignore_patterns('.git', 'log', 'tmp', 'storage', 'node_modules'))
        if self.native_frontend_manifest is not None:
            from .next40_route_frontend import apply_frontend_overlay
            self.native_route_environment_revision=apply_frontend_overlay(app,self.native_frontend_manifest,self.logs)
        for name in ('log', 'tmp', 'storage'):
            (app / name).mkdir(exist_ok=True)
        (app / 'config/database.yml').write_text('development:\n  adapter: postgresql\n  database: openstreetmap\n  username: openstreetmap\n  host: /state/run\n  encoding: utf8\n')
        (app / 'config/settings.local.yml').write_text('server_url: "127.0.0.1:' + str(port) + '"\nnominatim_url: "' + self.search_url + '/"\nfossgis_osrm_url: "http://127.0.0.1:"\n')
        engine = app / 'app/assets/javascripts/index/directions/fossgis_osrm.js'
        engine.write_text(remap_routing_ports(engine.read_text(), dict(zip(('car', 'bike', 'foot'), self.ports.ports[2:]))))
        leaflet_map = app / 'app/assets/javascripts/leaflet.map.js'
        leaflet_map.write_text(preserve_shortlink_port(leaflet_map.read_text()))
        if self.short_routes:
            from .map_short_route import patch
            controller=app/'app/controllers/site_controller.rb'
            js,ruby=patch(leaflet_map.read_text(),controller.read_text())
            leaflet_map.write_text(js);controller.write_text(ruby)
            atomic_write_json(self.logs/'short-route-extension.json',dict(
                version='local-compact-route-v1',original_benchmark_equivalence=False,
                coordinate_decimals=6,mutable_token_database=False,
                source='current public route URL and visible native route',
                source_hashes={str(p.relative_to(app)):hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in (leaflet_map,controller)}))
        if self.native_layer_refresh:
            from .map_native_renderer_index import patch_source,require_exact_private_source
            renderer=app/'vendor/assets/leaflet/leaflet.osm.js'
            original=renderer.read_text();renderer.write_text(patch_source(original))
            atomic_write_json(self.logs/'native-renderer-membership-index.json',
                require_exact_private_source(original,renderer.read_text(),None))
        if self.tile_url:
            tile_source = app / 'vendor/assets/leaflet/leaflet.osm.js'
            old = 'http://ogma.lti.cs.cmu.edu:8080/tile/'
            text = tile_source.read_text()
            if text.count(old) != 2:
                raise ValueError('Pinned native tile URL changed')
            tile_source.write_text(text.replace(old, self.tile_url + '/tile/'))
        if self.native_layer_refresh:
            from .map_native_layer_runtime import apply_frontend_refresh
            apply_frontend_refresh(app,self.logs)
        if self.native_share_observer:
            from .map_share_roundtrip import patch_readers
            names=('app/assets/javascripts/index.js','app/assets/javascripts/embed.js.erb')
            changes=patch_readers({n:(app/n).read_text()for n in names})
            for name,body in changes.items():(app/name).write_text(body)
            atomic_write_json(self.logs/'native-share-observer.json',dict(
                version='native-map-share-observer-v1',read_only=True,
                installed_before_baseline=True,files={n:hashlib.sha256((app/n).read_bytes()).hexdigest()for n in names}))
        self.event('prepare_native_frontend', started)
        if self.export_preload:
            from .map_export_preload import preload_controller
            controller=app/'app/controllers/api/map_controller.rb'
            controller.write_text(preload_controller(controller.read_text()))
            self.event('export_native_association_preload',time.monotonic(),renderer_changed=False)
        flags = self.flags(state)
        db = flags + [str(self.images / 'db.sif')]
        web = flags + ['--bind', str(app) + ':/app', '--pwd', '/app', '--env', 'RAILS_ENV=development', '--env', 'DISABLE_SPRING=1', *self.native_web_env, str(self.images / 'web.sif')]
        self.prepare_app_database(state,db)
        self.launch(db + ['postgres', '-D', '/state/pg', '-c', 'listen_addresses=', '-c', 'unix_socket_directories=/state/run', '-c', 'shared_buffers=128MB'], 'app_postgres')
        self.wait_postgres(db + ['pg_isready'], 'openstreetmap', 'app_postgres')
        if not self.with_geographic_baseline:
            self.run(db + ['createdb', '-h', '/state/run', '-U', 'openstreetmap', 'openstreetmap'], 'create_app_database')
        self.run(flags + [str(self.images / 'web.sif'), 'sh', '-c', 'cp -a /app/node_modules /state/app/node_modules'], 'copy_node_modules', 300)
        self.run(web + ['bundle', 'check'], 'bundle_check')
        if not self.with_geographic_baseline:
            self.run(web + ['bundle', 'exec', 'rails', 'db:migrate'], 'migrate_app_database', 300)
        if self.with_geographic_baseline and self.community_fixture is not None:
            from .map_write_sequences import calibrate
            atomic_write_json(self.logs / 'native-write-sequences.json', calibrate(self))
        self.rails_command = web + ['bundle', 'exec', 'rails', 'server', '-b', '127.0.0.1', '-p', str(port)]
        self.launch(self.rails_command, 'rails_server')
        # Rails compiles native assets on the first page request. Abandoning
        # that request every ten seconds leaves concurrent compilations in
        # Puma and starts more work. Keep one request within the total budget.
        began=time.monotonic();self.wait_http(self.url,180,request_seconds=180)
        self.event('frontend_http_ready',began)

    def app_sql(self, sql):
        state = self.state/'frontend'
        command = self.flags(state) + [str(self.images/'db.sif'), 'psql', '-XAt', '-v', 'ON_ERROR_STOP=1',
                    '-h', '/state/run', '-U', 'openstreetmap', '-d', 'openstreetmap']
        result = subprocess.run(command, input=sql, text=True, capture_output=True, timeout=60, check=True)
        return result.stdout.strip()

    def fingerprint(self):
        if self.reset_guard is None:
            raise RuntimeError('Map task state tracking was not enabled')
        return self.reset_guard.fingerprint()

    def reset_state(self):
        if getattr(self, '_reuse_invalid_reason', None):
            from .map_reset_guard import MapStateChanged
            raise MapStateChanged(self._reuse_invalid_reason)
        if self.reset_guard is None:
            raise RuntimeError('Map reset guard was not enabled')
        began = time.monotonic()
        self.reset_guard.require_unchanged()
        if self.provider_environment is not None:self.provider_environment.require_owned()
        self.restart_frontend(preserve_compiled_assets=not getattr(self, '_frontend_assets_changed', False))
        self.reset_guard.require_unchanged()
        if self.provider_environment is not None:self.provider_environment.require_owned()
        self._frontend_assets_changed = False
        self.event('reset_unchanged_app', began, database_writes=False, browser_context_reused=False)

    def restart_frontend(self, *, preserve_compiled_assets=False):
        """Internal service restart; callers still enforce task state/reset proofs."""
        self.stop_service('rails_server')
        app = self.state/'frontend/app'
        clear_frontend_transients(app,preserve_compiled_assets=preserve_compiled_assets)
        self.launch(self.rails_command, 'rails_server')
        self.wait_http(self.url,180,request_seconds=180)

    def __exit__(self, *args):
        for process in reversed(self.active):
            if process.poll() is not None:
                continue
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
        self.active = []
        for handle in self.handles:
            handle.close()
        self.handles = []
        try:
            if self.provider_environment is not None:
                self.provider_environment.close(); self.provider_environment = None
        finally:
            if self.ports:
                self.ports.close(); self.ports = None
            if self.temporary:
                self.temporary.cleanup(); self.temporary = None

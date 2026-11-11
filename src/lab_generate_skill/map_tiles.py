"""Native renderd/mod_tile service using the immutable PG15 WebArena snapshot."""
from pathlib import Path
import math
import os
import socket
import time
import xml.etree.ElementTree as ET


def rebind_mapnik_database(path):
    tree=ET.parse(path)
    for datasource in tree.findall('.//Datasource'):
        params={node.attrib.get('name'):node for node in datasource.findall('Parameter')}
        if params.get('type') is None or params['type'].text!='postgis':continue
        for key,value in [('host','/state/run'),('user','renderer'),('dbname','gis')]:
            node=params.get(key)
            if node is None:node=ET.SubElement(datasource,'Parameter',{'name':key})
            node.text=value
        for key in ('password','port'):
            if key in params:datasource.remove(params[key])
    tree.write(path,encoding='utf-8',xml_declaration=True)


def sample_tile_path():
    zoom=15;n=2**zoom;lon,lat=-73.9857,40.7484
    x=math.floor((lon+180)/360*n)
    y=math.floor((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)
    return f'/tile/{zoom}/{x}/{y}.png'


def missing_tile_load_limit(host_cpus):
    """mod_tile reads host loadavg, not the Slurm allocation's CPU count.

    Its native default (50) rejects healthy high-core shared hosts. Scale that
    guard to host capacity, retaining a finite limit and two renderer threads.
    """
    if type(host_cpus) is not int or host_cpus < 1:
        return 50
    return max(50,host_cpus)


def start_native_tiles(services,port):
    state=services.state/'tiles';images=services.images;data=images/'query-data/tiles'
    if not (data/'stage.json').is_file():raise ValueError('Tile snapshot stage missing')
    for name in ('run','tmp','tiles','log'):(state/name).mkdir(parents=True,mode=0o700)
    (state/'hosts').write_text('127.0.0.1 localhost '+socket.gethostname()+'\n')
    base=services.flags(state)+[str(images/'tiles.sif')]
    if os.environ.get('LAB_MAP_PARALLEL_TILE_CLONE')=='1':
        import sys
        script=Path(__file__).resolve().parents[2]/'scripts/clone_map_snapshot.py'
        services.run([sys.executable,str(script),'--source',str(data/'postgres'),'--destination',str(state/'postgres'),
                      '--progress',str(services.logs/'tile-clone-progress.json')],'clone_tile_database',900)
    else:
        services.run(['cp','-a','--reflink=auto',str(data/'postgres'),str(state/'postgres')],'clone_tile_database',900)
    (state/'postgres').chmod(0o700);(state/'postgres/postmaster.pid').unlink(missing_ok=True)
    (state/'postgresql.conf').write_text("data_directory='/state/postgres'\nhba_file='/state/pg_hba.conf'\nlisten_addresses=''\nunix_socket_directories='/state/run'\nshared_buffers=512MB\nmax_connections=24\nmax_parallel_workers=2\njit=off\n")
    (state/'pg_hba.conf').write_text('local all all trust\n')
    services.launch(base+['/usr/lib/postgresql/15/bin/postgres','-D','/state/postgres','-c','config_file=/state/postgresql.conf'],'tile_postgres')
    services.wait_postgres(base+['/usr/lib/postgresql/15/bin/pg_isready'],'renderer','tile_postgres')
    services.run(base+['cp','-a','/home/renderer/src/openstreetmap-carto-backup','/state/style'],'copy_native_tile_style')
    services.run(base+['sh','-ec','cd /state/style; carto project.mml > mapnik.xml'],'compile_native_tile_style',180)
    rebind_mapnik_database(state/'style/mapnik.xml')
    (state/'renderd.conf').write_text('''[renderd]
stats_file=/state/run/renderd.stats
socketname=/state/run/renderd.sock
num_threads=2
tile_dir=/state/tiles
[mapnik]
plugins_dir=/usr/lib/mapnik/3.1/input
font_dir=/usr/share/fonts
font_dir_recurse=true
[default]
URI=/tile/
TILEDIR=/state/tiles
XML=/state/style/mapnik.xml
HOST=localhost
TILESIZE=256
MAXZOOM=20
''')
    render_command=['renderd','-f','-c','/state/renderd.conf']
    if os.environ.get('LAB_MAP_RENDER_DEBUG')=='1':render_command=['env','G_MESSAGES_DEBUG=all']+render_command
    renderer=services.launch(base+render_command,'renderd')
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        if renderer.poll() is not None:raise RuntimeError('Native renderd exited')
        if (state/'run/renderd.sock').exists():break
        time.sleep(.1)
    else:raise TimeoutError('Native renderd socket readiness')
    (state/'apache.conf').write_text('''ServerRoot /etc/apache2
ServerName 127.0.0.1
DefaultRuntimeDir /state/run
PidFile /state/run/apache.pid
Listen 127.0.0.1:PORT
IncludeOptional /etc/apache2/mods-enabled/*.load
IncludeOptional /etc/apache2/mods-enabled/*.conf
User www-data
Group www-data
ErrorLog /dev/stderr
LogFormat "%h %t \\"%r\\" %>s %b %D" lab_tiles
CustomLog /dev/stdout lab_tiles
LogLevel warn tile:info
DocumentRoot /var/www/html
<Directory /var/www/html>
Require all granted
</Directory>
LoadTileConfigFile /state/renderd.conf
ModTileRenderdSocketName /state/run/renderd.sock
ModTileRequestTimeout 0
ModTileMissingRequestTimeout 90
ModTileMaxLoadMissing HOST_LOAD_LIMIT
'''.replace('PORT',str(port)).replace('HOST_LOAD_LIMIT',str(missing_tile_load_limit(os.cpu_count()))))
    from .io_utils import atomic_write_json
    atomic_write_json(services.logs/'tile-load-policy.json',{
        'host_logical_cpus':os.cpu_count(),'max_load_missing':missing_tile_load_limit(os.cpu_count()),
        'render_threads':2,'missing_request_timeout_seconds':90,'scope':'Native host loadavg guard, not per-job CPU allocation',
        'upstream':'https://github.com/openstreetmap/mod_tile/blob/master/includes/render_config.h'})
    # LoadTileConfigFile already registers the layer and its private TILEDIR.
    # AddTileConfig also registers it, with the compiled-in default TILEDIR;
    # the duplicate first route can otherwise read the wrong cache directory.
    (services.logs/'tile-apache.conf').write_text((state/'apache.conf').read_text())
    (services.logs/'tile-renderd.conf').write_text((state/'renderd.conf').read_text())
    apache=services.flags(state)+['--env','APACHE_RUN_DIR=/state/run','--env','APACHE_LOCK_DIR=/state/run','--env','APACHE_LOG_DIR=/state/log',str(images/'tiles.sif')]
    services.run(apache+['apache2','-t','-f','/state/apache.conf'],'check_tile_apache')
    services.launch(apache+['apache2','-DFOREGROUND','-f','/state/apache.conf'],'tile_http')
    url='http://127.0.0.1:'+str(port)
    first=services.wait_http(url+sample_tile_path(),90)
    second=services.wait_http(url+sample_tile_path(),30)
    if not first.startswith(b'\x89PNG\r\n\x1a\n') or len(first)<1000 or first!=second:raise RuntimeError('Native tile HTTP rendering/deterministic cache probe failed')
    (services.logs/'http-tile.png').write_bytes(first)
    return url

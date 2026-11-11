"""Original native service settings; only private paths and leased ports vary."""

import math
from lab_generate_skill.domain.map_services import MapServiceSpec


def sample_tile_path() -> str:
    zoom = 15
    n = 2**zoom
    lon, lat = -73.9857, 40.7484
    x = math.floor((lon + 180) / 360 * n)
    y = math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return f"/tile/{zoom}/{x}/{y}.png"


POSTGRES = "data_directory='/state/postgres'\nhba_file='/state/pg_hba.conf'\nlisten_addresses=''\nunix_socket_directories='/state/run'\nshared_buffers=512MB\nmax_connections=24\nmax_parallel_workers=2\njit=off\n"
SEARCH_ENV = 'NOMINATIM_DATABASE_DSN="pgsql:dbname=nominatim;host=/state/run;user=nominatim"\nNOMINATIM_DATABASE_WEBUSER="nominatim"\nNOMINATIM_REPLICATION_URL=""\n'
SEARCH_ROUTER = r"""<?php
$path=parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
if (!preg_match('~^/(search|reverse|lookup|details|status|polygons|deletable)(?:\.php)?/?$~', $path, $m)) {
    http_response_code(404); echo 'Unknown local map endpoint'; return;
}
require '/state/project/website/'.$m[1].'.php';
"""
RENDERD = """[renderd]
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
"""
APACHE = """ServerRoot /etc/apache2
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
ModTileMissingRequestTimeout 30
ModTileMaxLoadMissing HOST_LOAD_LIMIT
"""


def validate_host(*, hostname: str, host_cpus: int) -> None:
    """Validate explicit observations before any private instance effect."""
    if (
        type(hostname) is not str
        or not hostname
        or len(hostname) > 253
        or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-."
            for c in hostname
        )
    ):
        raise ValueError("Actual safe native hostname required")
    if type(host_cpus) is not int or host_cpus < 1:
        raise ValueError("Observed host CPU count required, not job allocation count")


def controls(spec: MapServiceSpec, *, hostname: str, host_cpus: int) -> dict[str, str]:
    spec = MapServiceSpec.model_validate(spec)
    validate_host(hostname=hostname, host_cpus=host_cpus)
    result: dict[str, str] = {}
    for service in ("search", "tiles", "frontend"):
        result[service + "/hosts"] = (
            "127.0.0.1 localhost "
            + hostname
            + "\n"
            + ("::1 localhost\n" if service != "tiles" else "")
        )
    for service in ("search", "tiles"):
        result[service + "/postgresql.conf"] = POSTGRES
        result[service + "/pg_hba.conf"] = "local all all trust\n"
    result.update(
        {
            "search/project/.env": SEARCH_ENV,
            "search/project/router.php": SEARCH_ROUTER,
            "tiles/renderd.conf": RENDERD,
            "tiles/apache.conf": APACHE.replace("PORT", str(spec.ports.tiles)).replace(
                "HOST_LOAD_LIMIT", str(max(50, host_cpus))
            ),
            "frontend/database.yml": "development:\n  adapter: postgresql\n  database: openstreetmap\n  username: openstreetmap\n  host: /state/run\n  encoding: utf8\n",
            "frontend/settings.local.yml": f'server_url: "127.0.0.1:{spec.ports.web}"\nnominatim_url: "http://127.0.0.1:{spec.ports.search}/"\nfossgis_osrm_url: "http://127.0.0.1:"\n',
        }
    )
    return result

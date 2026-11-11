"""Private immutable controls; persistent application writes stay under state."""

from pathlib import Path
import stat
from lab_generate_skill.ports.lifecycle import OperationControl
from .service_contract import ShoppingServiceSpec
from .service_programs import MAIL_SINK

FPM = """[global]
pid=/runtime/php.pid
error_log=/runtime/php-error.log
daemonize=no
[www]
listen=/runtime/php.sock
pm=ondemand
pm.max_children=4
clear_env=no
catch_workers_output=yes
php_admin_value[session.save_path]=/state/var/session
php_admin_value[upload_tmp_dir]=/state/uploads
php_admin_value[sys_temp_dir]=/state/uploads
php_admin_value[memory_limit]=1024M
php_admin_value[sendmail_path]=/usr/bin/env php /control/mail-sink.php
"""
NGINX = """worker_processes 2;
pid /runtime/nginx.pid;
error_log /runtime/nginx-error.log;
events { worker_connections 512; }
http { include /etc/nginx/mime.types;
access_log /runtime/nginx-access.log;
client_body_temp_path /state/nginx/client;
proxy_temp_path /state/nginx/proxy;
fastcgi_temp_path /state/nginx/fastcgi;
upstream fastcgi_backend { server unix:/runtime/php.sock; }
server { listen 127.0.0.1:WEB_PORT; server_name 127.0.0.1;
set $MAGE_ROOT /var/www/magento2; include /var/www/magento2/nginx.conf.sample; }
}
"""


def checked(path: Path, control: OperationControl) -> None:
    for part in (*reversed(path.parents), path):
        control.checkpoint()
        try:
            mode = part.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode) or (part != path and not stat.S_ISDIR(mode)):
            raise ValueError("Unsafe private Shopping path")


def write_controls(spec: ShoppingServiceSpec, control: OperationControl) -> None:
    state, root = Path(spec.files.state_root), Path(spec.control_root)
    # Magento's nginx.conf.sample resolves its relative include against the
    # enclosing config directory. Preserve these exact pinned image bytes.
    source = state / "fastcgi_params"
    checked(source, control)
    native_fastcgi = source.read_bytes()
    if not native_fastcgi or len(native_fastcgi) > 65536:
        raise ValueError("Missing or oversized original FastCGI parameters")
    target = root / "fastcgi_params"
    checked(target, control)
    with target.open("xb") as stream:
        stream.write(native_fastcgi)
    target.chmod(0o600)
    config = state / "search/config/elasticsearch.yml"
    checked(config, control)
    original = "\n".join(
        line
        for line in config.read_text().splitlines()
        if line.split(":", 1)[0].strip()
        not in {
            "network.host",
            "http.port",
            "transport.port",
            "discovery.type",
            "node.processors",
            "path.data",
            "path.logs",
        }
    )
    config.write_text(original + f"""
network.host: 127.0.0.1
http.port: {spec.ports.search}
transport.port: {spec.ports.transport}
discovery.type: single-node
node.processors: 2
path.data: /usr/share/java/elasticsearch/data
path.logs: /usr/share/java/elasticsearch/logs
""")
    options = state / "search/config/jvm.options.d"
    checked(options, control)
    options.mkdir(mode=0o700, exist_ok=True)
    settings = {
        root / "php.conf": FPM,
        root / "nginx.conf": NGINX.replace("WEB_PORT", str(spec.ports.web)),
        root / "mail-sink.php": "<?php\n" + MAIL_SINK,
        options
        / "shopping.options": "-Xms512m\n-Xmx512m\n-XX:ActiveProcessorCount=2\n",
    }
    for path, content in settings.items():
        checked(path, control)
        with path.open("x") as stream:
            stream.write(content)
        path.chmod(0o600)
    control.checkpoint()

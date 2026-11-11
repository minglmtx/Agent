"""Render original Magento runtime configuration into an owned private seed."""

from pathlib import Path
from lab_generate_skill.ports.lifecycle import OperationControl
from .artifact_io import checked_path
from .service_contract import AdminServiceSpec
from .service_programs import MAIL_SINK

FPM = """[global]
pid = /state/run/php-fpm.pid
error_log = /state/php-error.log
daemonize = no
[www]
listen = /state/run/php-fpm.sock
pm = ondemand
pm.max_children = 8
pm.process_idle_timeout = 10s
catch_workers_output = yes
clear_env = no
php_admin_value[sendmail_path] = /usr/bin/env php /state/mail-sink.php
php_admin_value[upload_tmp_dir] = /state/php-upload
php_admin_value[sys_temp_dir] = /state/php-upload
php_admin_value[memory_limit] = 2048M
php_admin_value[error_log] = /state/php-worker.log
php_admin_value[session.save_path] = /state/app/var/session
"""

NGINX = """worker_processes 2;
pid /state/run/nginx.pid;
error_log /state/nginx-error.log;
events { worker_connections 512; }
http {
 include /etc/nginx/mime.types;
 access_log /state/nginx-access.log;
 client_body_temp_path /state/nginx/client;
 proxy_temp_path /state/nginx/proxy;
 fastcgi_temp_path /state/nginx/fastcgi;
 upstream fastcgi_backend { server unix:/state/run/php-fpm.sock; }
 server {
 listen 127.0.0.1:WEB_PORT;
 server_name 127.0.0.1;
 set $MAGE_ROOT /var/www/magento2;
 include /var/www/magento2/nginx.conf.sample;
 }
}
"""


def write_service_files(spec: AdminServiceSpec, control: OperationControl) -> None:
    spec = AdminServiceSpec.model_validate(spec)
    state = Path(spec.layout.state_root)
    for name in (
        "nginx/client",
        "nginx/proxy",
        "nginx/fastcgi",
        "app/var/session",
        "php-upload",
        "elasticsearch/config/jvm.options.d",
        "elasticsearch/snapshots",
    ):
        target = state / name
        checked_path(target, control)
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
    config = state / "elasticsearch/config/elasticsearch.yml"
    checked_path(config, control)
    # Original image configuration retains its defaults; override only addresses.
    keys = {
        "network.host",
        "http.port",
        "transport.port",
        "discovery.type",
        "node.processors",
        "path.data",
        "path.logs",
        "path.repo",
    }
    original = "\n".join(
        line
        for line in config.read_text().splitlines()
        if line.split(":", 1)[0].strip() not in keys
    )
    search = original + f"""
network.host: 127.0.0.1
http.port: {spec.ports.search}
transport.port: {spec.ports.transport}
discovery.type: single-node
node.processors: 2
path.data: /usr/share/java/elasticsearch/data
path.logs: /usr/share/java/elasticsearch/logs
path.repo: ["/state/elasticsearch/snapshots"]
"""
    files = {
        "php-fpm.conf": FPM,
        "nginx.conf": NGINX.replace("WEB_PORT", str(spec.ports.web)),
        "mail-sink.php": MAIL_SINK,
        "elasticsearch/config/elasticsearch.yml": search,
        "elasticsearch/config/jvm.options.d/pilot.options": "-Xms512m\n-Xmx512m\n-XX:ActiveProcessorCount=2\n",
    }
    for name, content in files.items():
        target = state / name
        checked_path(target, control)
        target.write_text(content)
        target.chmod(0o600)
    control.checkpoint()

"""Immutable controls; sessions, upload/cache and native DB stay in state."""

from pathlib import Path
import stat
from lab_generate_skill.ports.lifecycle import OperationControl
from .service_contract import RedditServiceSpec

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
env[DATABASE_URL]="postgresql://postmill@localhost/postmill?host=/runtime&port=DATABASE_PORT"
php_admin_value[session.save_path]=/state/session
php_admin_value[upload_tmp_dir]=/state/uploads
php_admin_value[sys_temp_dir]=/state/uploads
php_admin_value[memory_limit]=1024M
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
server { listen 127.0.0.1:WEB_PORT; server_name 127.0.0.1;
root /var/www/html/public; index index.php;
location ^~ /submission_images/ { root /state/media-native; try_files $uri @original_native_media; }
location ^~ /media/cache/ { root /state/media-native; try_files $uri @original_native_media; }
location @original_native_media { root /var/www/html/public; try_files $uri =404; }
location / { try_files $uri /index.php$is_args$args; }
location ~ \\.php$ { include /etc/nginx/fastcgi_params;
fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
fastcgi_pass unix:/runtime/php.sock; }
} }
"""


def checked(path: Path, control: OperationControl) -> None:
    for part in (*reversed(path.parents), path):
        control.checkpoint()
        try:
            mode = part.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode) or (part != path and not stat.S_ISDIR(mode)):
            raise ValueError("Unsafe original private Reddit path")


def write_controls(spec: RedditServiceSpec, control: OperationControl) -> None:
    root = Path(spec.control_root)
    settings = {
        root / "php.conf": FPM.replace("DATABASE_PORT", str(spec.ports.database)),
        root / "nginx.conf": NGINX.replace("WEB_PORT", str(spec.ports.web)),
        root / "pg_hba.conf": "local all all trust\n",
    }
    for path, text in settings.items():
        checked(path, control)
        with path.open("x") as stream:
            stream.write(text)
        path.chmod(0o600)
    control.checkpoint()

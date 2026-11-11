"""Rootless worker-local Shopping/Reddit services using the pinned SIF snapshots.

Static application code and published media remain in the read-only SIF. Only
mutable database/config/cache state is copied. Initial coverage is navigation;
media uploads and outbound delivery require separate capability admission.
"""
import getpass,hashlib,json,os,subprocess,tempfile,time,urllib.request,urllib.error
from pathlib import Path
from .admin_ports import PortLease
from .runtime_diagnostics import runtime_phase

class IsolatedContentSite:
    def __init__(self,root,logs,domain,*,capture_mail=False,inactive_product_payments=True):
        if domain not in ('shopping','reddit'):raise ValueError('Unsupported content site')
        if capture_mail and domain!='shopping':raise ValueError('Mail capture currently supports Magento only')
        if type(inactive_product_payments) is not bool:raise ValueError("Explicit native product payment policy required")
        self.inactive_product_payments=inactive_product_payments
        self.capture_mail=capture_mail
        self.root=Path(root);self.logs=Path(logs);self.domain=domain;self.processes=[];self.handles=[]
    def command(self,args,**kwargs):
        return subprocess.run(self.base+args,check=True,timeout=kwargs.pop('timeout',180),**kwargs)
    def launch(self,name,args,extra=None):
        append=getattr(self,'_service_log_append',False)
        h=(self.logs/(name+'.log')).open('a' if append else 'w');self.handles.append(h)
        if append:
            h.write('\n--- service restart generation %s ---\n'%getattr(self,'generation',0));h.flush()
        p=subprocess.Popen((extra or self.base)+args,stdout=h,stderr=subprocess.STDOUT);self.processes.append(p)
    def __enter__(self):
        if not os.getenv('SLURM_JOB_ID') or not os.getenv('TMPDIR'):raise RuntimeError('CPU Slurm allocation required')
        self.logs.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix=self.domain+'-site-',dir=os.environ['TMPDIR']);self.state=Path(self.temp.name)
        for name in ('tmp','var-tmp','mysql-tmp'):(self.state/name).mkdir(mode=0o700)
        self.ports=PortLease(count=5);web,db,redis,search,transport=self.ports.ports;self.url=f'http://127.0.0.1:{web}'
        image=self.root/'containers/webarena'/f'{self.domain}.sif'
        flags=['apptainer','exec','--cleanenv','--containall','--no-home','--no-mount','bind-paths,hostfs,cwd','--pwd','/','--bind',str(self.state)+':/state','--bind',str(self.state/'tmp')+':/tmp','--bind',str(self.state/'var-tmp')+':/var/tmp']
        bare=flags+[str(image)]
        try:
            with runtime_phase(self.logs,'extract_mutable_state'):
                if self.domain=='shopping':
                    script='set -eu; cp -a /var/lib/mysql /state/mysql; cp -a /var/www/magento2/app/etc /state/etc; cp -a /var/www/magento2/generated /state/generated; mkdir -p /state/var /state/search/logs /state/search/tmp; cp -a /usr/share/java/elasticsearch/config /state/search/config; cp -a /usr/share/java/elasticsearch/data /state/search/data; cp /etc/nginx/fastcgi_params /state/fastcgi_params; chmod -R u+rwX /state/mysql /state/etc /state/generated /state/search'
                else:
                    script='set -eu; cp -a /usr/local/pgsql/data /state/postgres; cp /var/www/html/.env /state/app.env; mkdir -p /state/var; chmod -R u+rwX /state/postgres; rm -f /state/postgres/postmaster.pid'
                subprocess.run(bare+['sh','-ec',script],check=True,timeout=600)
            for sub in ('run','nginx','redis','uploads'):(self.state/sub).mkdir(exist_ok=True,mode=0o700)
            if self.capture_mail:
                from .local_mail_capture import prepare
                self.mail_outbox=prepare(self.state)
            bindings=[]
            if self.domain=='shopping':
                for source,target in [('mysql','/var/lib/mysql'),('etc','/var/www/magento2/app/etc'),('generated','/var/www/magento2/generated'),('var','/var/www/magento2/var'),('search/config','/usr/share/java/elasticsearch/config'),('search/data','/usr/share/java/elasticsearch/data'),('search/logs','/usr/share/java/elasticsearch/logs')]:bindings+=['--bind',str(self.state/source)+':'+target]
            else:
                (self.state/'postgres').chmod(0o700)
                # Peer/local access is protected by the private 0700 socket dir;
                # TCP retains password authentication from the original env.
                (self.state/'pg_hba.conf').write_text('local all all trust\nhost all all 127.0.0.1/32 md5\n')
                import re
                env=(self.state/'app.env').read_text()
                match=re.search(r'^DATABASE_URL=(.*)$',env,re.M)
                if not match:raise RuntimeError('Missing original database URL')
                # Docker startup supplied the populated DB binding; .env contains
                # development placeholders. Use its real role via private socket.
                value=f'postgresql://postmill@localhost/postmill?host=/state/run&port={db}'
                self.database_url=value
                env=re.sub(r'^DATABASE_URL=.*$',lambda _: 'DATABASE_URL='+value,env,flags=re.M)
                env=re.sub(r'^ENABLE_EXPERIMENTAL_REST_API=.*$','ENABLE_EXPERIMENTAL_REST_API=1',env,flags=re.M)
                if 'ENABLE_EXPERIMENTAL_REST_API=' not in env:env+='\nENABLE_EXPERIMENTAL_REST_API=1\n'
                (self.state/'app.env').write_text(env);(self.state/'app.env').chmod(0o600)
                for source,target in [('postgres','/usr/local/pgsql/data'),('app.env','/var/www/html/.env'),('var','/var/www/html/var')]:bindings+=['--bind',str(self.state/source)+':'+target]
            if self.domain=='shopping':
                from .shopping_native_static_assets import prepare_native_assets
                native_bindings,self.native_static_assets=prepare_native_assets(self.state,bare)
                bindings+=native_bindings
                (self.logs/'native-static-assets.json').write_text(json.dumps(self.native_static_assets,indent=2)+'\n')
                if self.inactive_product_payments:
                    from .shopping_native_inactive_buttons import prepare_native_layout
                    native_payment_bindings,self.native_payment_layout=prepare_native_layout(self.state,bare)
                    bindings+=native_payment_bindings
            self.base=flags+bindings+[str(image)]
            php='''[global]
pid=/state/run/php.pid
error_log=/state/php-error.log
daemonize=no
[www]
listen=/state/run/php.sock
pm=ondemand
pm.max_children=4
clear_env=no
catch_workers_output=yes
php_admin_value[session.save_path]=/state/run
php_admin_value[upload_tmp_dir]=/state/uploads
php_admin_value[sys_temp_dir]=/state/uploads
php_admin_value[memory_limit]=1024M
'''
            if self.domain=='reddit':php+='env[DATABASE_URL]='+json.dumps(self.database_url)+'\n'
            if self.capture_mail:php+='php_admin_value[sendmail_path]=/bin/sh /state/capture-mail.sh\n'
            (self.state/'php.conf').write_text(php)
            if self.domain=='shopping':
                web_body='set $MAGE_ROOT /var/www/magento2; include /var/www/magento2/nginx.conf.sample;'
            else:
                web_body='''root /var/www/html/public; index index.php;
location / { try_files $uri /index.php$is_args$args; }
location ~ \\.php$ { include /etc/nginx/fastcgi_params; fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name; fastcgi_pass unix:/state/run/php.sock; }
'''
            nginx='''worker_processes 2;
pid /state/run/nginx.pid;
error_log /state/nginx-error.log;
events { worker_connections 512; }
http { include /etc/nginx/mime.types; access_log /state/nginx-access.log;
client_body_temp_path /state/nginx/client; proxy_temp_path /state/nginx/proxy; fastcgi_temp_path /state/nginx/fastcgi;
upstream fastcgi_backend { server unix:/state/run/php.sock; }
server { listen 127.0.0.1:PORT; server_name 127.0.0.1; BODY }
}
'''.replace('PORT',str(web)).replace('BODY',web_body)
            (self.state/'nginx.conf').write_text(nginx)
            if self.domain=='shopping':
                self.launch('mysql',['mysqld','--no-defaults','--datadir=/state/mysql','--tmpdir=/state/mysql-tmp','--socket=/state/run/mysql.sock','--pid-file=/state/run/mysql.pid','--bind-address=127.0.0.1',f'--port={db}','--innodb-buffer-pool-size=256M'])
                self.wait_command(['mysqladmin','--socket=/state/run/mysql.sock','ping'],120)
                self.launch('redis',['redis-server','--bind','127.0.0.1','--port',str(redis),'--dir','/state/redis','--save','','--appendonly','no'])
                cfg=self.state/'search/config/elasticsearch.yml'
                with cfg.open('a') as f:f.write(f'\nnetwork.host: 127.0.0.1\nhttp.port: {search}\ntransport.port: {transport}\ndiscovery.type: single-node\nnode.processors: 2\n')
                options=self.state/'search/config/jvm.options.d';options.mkdir(exist_ok=True)
                (options/'local.options').write_text('-Xms512m\n-Xmx512m\n-XX:ActiveProcessorCount=2\n')
                self.launch('elasticsearch',['elasticsearch'],extra=flags+bindings+['--env','ES_JAVA_HOME=/usr','--env','ES_TMPDIR=/state/search/tmp',str(image)])
                self.wait_http(f'http://127.0.0.1:{search}/_cluster/health',120)
                (self.state/'configure.php').write_text('''<?php
$p='/var/www/magento2/app/etc/env.php';$e=include $p;
$e['db']['connection']['default']['host']='127.0.0.1:'.$argv[1];unset($e['db']['connection']['default']['port']);
foreach($e['cache']['frontend'] as &$c){$c['backend_options']['server']='127.0.0.1';$c['backend_options']['port']=(int)$argv[2];}unset($c);
if(($e['session']['save']??'')==='redis'){$e['session']['redis']['host']='127.0.0.1';$e['session']['redis']['port']=(int)$argv[2];}
if(($argv[5]??'')==='capture'){
    $e['system']['default']['system']['smtp']['transport']='sendmail';
    $e['system']['default']['system']['smtp']['disable']='0';
}
file_put_contents($p,"<?php\\nreturn ".var_export($e,true).";\\n");
$d=$e['db']['connection']['default'];$pdo=new PDO('mysql:host=127.0.0.1;port='.$argv[1].';dbname='.$d['dbname'],$d['username'],$d['password']);
$st=$pdo->prepare("UPDATE core_config_data SET value=? WHERE path IN ('web/unsecure/base_url','web/secure/base_url')");$st->execute([$argv[3].'/']);
$st=$pdo->prepare("INSERT INTO core_config_data(scope,scope_id,path,value) VALUES('default',0,?,?) ON DUPLICATE KEY UPDATE value=VALUES(value)");
foreach(['opensearch','elasticsearch7','elasticsearch6','elasticsearch'] as $engine){$st->execute(['catalog/search/'.$engine.'_server_hostname','127.0.0.1']);$st->execute(['catalog/search/'.$engine.'_server_port',$argv[4]]);}
''')
                self.command(['php','/state/configure.php',str(db),str(redis),self.url,str(search),'capture' if self.capture_mail else 'native'],stdout=subprocess.DEVNULL)
                if self.inactive_product_payments:
                    from .shopping_native_inactive_buttons import confirm_native_inactive
                    self.native_payment_layout=confirm_native_inactive(self,self.native_payment_layout)
                if self.capture_mail:
                    # Native Magento rejects an env.php system configuration
                    # change until its deployment configuration is imported.
                    # Keep the check enabled; synchronize the worker-local DB
                    # before exposing HTTP or attempting a subscription.
                    with runtime_phase(self.logs,'mail_configuration_import'):
                        self.command(['php','/var/www/magento2/bin/magento','app:config:import','--no-interaction'],stdout=subprocess.DEVNULL)
                self.command(['php','/var/www/magento2/bin/magento','cache:flush'],stdout=subprocess.DEVNULL)
            else:
                self.launch('postgres',['postgres','-D','/state/postgres','-h','127.0.0.1','-p',str(db),'-k','/state/run','-c','hba_file=/state/pg_hba.conf'])
                self.wait_command(['pg_isready','-h','/state/run','-p',str(db),'-U','postmill','-d','postmill'],120)
                self.db_port=db
                # Same account setup as Go-Browse/webarena-reset/reddit-reset.sh.
                self.command(['psql','-h','/state/run','-p',str(db),'-U','postmill','-d','postmill','-c',"UPDATE users SET trusted=true WHERE username='MarvelsGrantMan136'"],stdout=subprocess.DEVNULL)
            self.command(['php-fpm','--test','--fpm-config','/state/php.conf'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.launch('php-fpm',['php-fpm','--nodaemonize','--fpm-config','/state/php.conf'])
            self.launch('nginx',['nginx','-e','/state/nginx-error.log','-c','/state/nginx.conf','-g','daemon off;'])
            with runtime_phase(self.logs,'http_startup'):
                self.wait_http(self.url+'/',180)
            return self
        except BaseException:self.__exit__(None,None,None);raise
    def wait_command(self,args,seconds):
        from .service_readiness import wait_for_command
        def record(row):
            with (self.logs/'database-readiness.jsonl').open('a') as stream:
                stream.write(json.dumps(row)+'\n')
        return wait_for_command(self.base+args,total_timeout=seconds,
                                service_running=lambda:all(p.poll() is None for p in self.processes),
                                record=record)
    def wait_http(self,url,seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if any(p.poll() is not None for p in self.processes):raise RuntimeError('Site service exited; inspect logs')
            try:
                with urllib.request.urlopen(url,timeout=min(30,max(1,end-time.monotonic()))) as r:
                    if r.status==200:
                        (self.logs/'http-readiness.json').write_text(json.dumps({'status':'ready','http_code':200}))
                        return
            except (urllib.error.URLError,TimeoutError) as exc:
                (self.logs/'http-readiness.json').write_text(json.dumps({'status':'pending','http_code':getattr(exc,'code',None),'exception_type':type(exc).__name__,'remaining_seconds':max(0,end-time.monotonic())}))
            time.sleep(1)
        raise TimeoutError('Site HTTP readiness exceeded budget')
    def fingerprint(self, *, include_orders=True):
        if self.domain=='reddit':
            sql='COPY (SELECT id,username,trusted FROM users ORDER BY id) TO STDOUT WITH CSV'
            data=self.command(['psql','-h','/state/run','-p',str(self.db_port),'-U','postmill','-d','postmill','-c',sql],capture_output=True).stdout
        else:
            code='''$e=include "/var/www/magento2/app/etc/env.php";$d=$e["db"]["connection"]["default"];$h=explode(":",$d["host"]);$p=new PDO("mysql:host=".$h[0].";port=".$h[1].";dbname=".$d["dbname"],$d["username"],$d["password"]);$v=[];foreach(["catalog_product_entity"=>"entity_id,sku","customer_entity"=>"entity_id,email","sales_order"=>"entity_id,increment_id,status"] as $t=>$fields){$v[$t]=$p->query("SELECT ".$fields." FROM ".$t." ORDER BY entity_id")->fetchAll(PDO::FETCH_ASSOC);}echo json_encode($v);'''
            if not include_orders:
                # Purchase evaluators separately verify the full original order
                # records and exactly one allowed new order. Other families
                # continue protecting orders with the original fingerprint.
                code=code.replace(',"sales_order"=>"entity_id,increment_id,status"','')
            data=self.command(['php','-r',code],capture_output=True).stdout
        return hashlib.sha256(data).hexdigest()
    def __exit__(self,*args):
        for p in reversed(self.processes):
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=10)
                except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
        for h in self.handles:h.close()
        if hasattr(self,'state'):
            for name in ('php-error.log','nginx-error.log','nginx-access.log','var/log/prod.log','var/log/dev.log','var/log/system.log','var/log/exception.log'):
                source=self.state/name
                if source.is_file():
                    with source.open('rb') as f:f.seek(max(0,source.stat().st_size-131072));(self.logs/name.replace('/','-')).write_bytes(f.read())
        if hasattr(self,'ports'):self.ports.close()
        if hasattr(self,'temp'):self.temp.cleanup()

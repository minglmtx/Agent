"""Fixed native Postmill programs; neither supplied task values nor old drivers."""

SEED = r"""set -eu
cp -a -- /usr/local/pgsql/data /state/postgres
cp -- /var/www/html/.env /state/app.env
chmod -R u+rwX /state/postgres
chmod 0700 /state/postgres
chmod 0600 /state/app.env
if [ -e /state/postgres/postmaster.pid ] || [ -L /state/postgres/postmaster.pid ]; then
 [ -f /state/postgres/postmaster.pid ] && [ ! -L /state/postgres/postmaster.pid ]
 rm -- /state/postgres/postmaster.pid
fi
for name in var tmp var-tmp uploads session nginx media-native; do
 mkdir -m 0700 /state/"$name"
done
for name in client proxy fastcgi; do mkdir -m 0700 /state/nginx/"$name"; done
"""

CONFIGURE = r"""
$port=filter_var($argv[1]??null,FILTER_VALIDATE_INT,['options'=>['min_range'=>1024,'max_range'=>65535]]);
if($port===false)throw new RuntimeException('Invalid native Postmill port');
$path='/state/app.env';$s=lstat($path);
if(!$s||is_link($path)||!is_file($path)||$s['nlink']!==1||$s['size']>65536)throw new RuntimeException('Bounded original private environment required');
$raw=file_get_contents($path);
$values=['DATABASE_URL'=>'"postgresql://postmill@localhost/postmill?host=/runtime&port='.$port.'"','UPLOAD_DSN'=>'"file:///state/media-native"','UPLOAD_ROOT'=>'"/"'];
foreach($values as $key=>$value){
    $pattern='/^'.preg_quote($key,'/').'=[^\r\n]*$/m';
    if(preg_match_all($pattern,$raw)!==1)throw new RuntimeException('Original native setting shape differs');
    $raw=preg_replace_callback($pattern,static fn()=>$key.'='.$value,$raw,1);
}
$pattern='/^ENABLE_EXPERIMENTAL_REST_API=[^\r\n]*$/m';$count=preg_match_all($pattern,$raw);
if($count>1)throw new RuntimeException('Duplicate native REST setting');
$raw=$count===1?preg_replace($pattern,'ENABLE_EXPERIMENTAL_REST_API=1',$raw,1):rtrim($raw,"\r\n")."\nENABLE_EXPERIMENTAL_REST_API=1\n";
if(file_put_contents($path,$raw)!==strlen($raw)||!chmod($path,0600))throw new RuntimeException('Native environment write incomplete');
echo 'configured';
"""

POSTGRES_READY = r"""set +e
/usr/bin/pg_isready -h /runtime -p "$1" -U postmill -d postmill >/dev/null
code=$?
case "$code" in 0) printf ready;; 1|2) printf waiting;; *) exit "$code";; esac
"""

# Match the exact original private-site startup account initialization. This
# happens once, before the task snapshot, and never creates or replaces a user.
TRUST_ACCOUNT = """BEGIN;
DO $$ BEGIN
IF (SELECT count(*) FROM users WHERE username='MarvelsGrantMan136')<>1 THEN
 RAISE EXCEPTION 'Original Postmill benchmark account missing or ambiguous';
END IF;
UPDATE users SET trusted=true WHERE username='MarvelsGrantMan136';
END $$;
COMMIT;
SELECT 'trusted';
"""

HTTP_READY = r"""
$port=filter_var($argv[1]??null,FILTER_VALIDATE_INT,['options'=>['min_range'=>1024,'max_range'=>65535]]);
if($port===false)throw new RuntimeException('Invalid native Postmill web port');
if(!is_file('/runtime/php.pid')||!file_exists('/runtime/php.sock')){echo 'waiting';exit;}
$context=stream_context_create(['http'=>['timeout'=>1,'ignore_errors'=>true,'follow_location'=>0]]);
$h=@fopen('http://127.0.0.1:'.$port.'/','rb',false,$context);
if($h===false){echo 'waiting';exit;}
$body=stream_get_contents($h,4096);fclose($h);
$headers=$http_response_header??[];
$ready=isset($headers[0])&&preg_match('~^HTTP/\S+ (2\d\d|3\d\d)(?: |$)~',$headers[0])&&is_string($body)&&stripos($body,'<html')!==false;
echo $ready?'ready':'waiting';
"""

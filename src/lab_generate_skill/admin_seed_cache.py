"""Worker-local pristine offline image extraction cache, before any services run.

Every task still gets independent mysql/app/search files. No hard links or reuse
of task-mutated state. Cache is opt-in until real reset controls pass.
"""
import fcntl,hashlib,json,os,subprocess,tempfile,time
from pathlib import Path

EXTRACT="cp -a /var/lib/mysql /state/mysql; cp -a /var/www/magento2 /state/app; chmod -R u+rwX /state/mysql /state/app; mkdir -p /state/run /state/redis /state/nginx; cp /etc/nginx/fastcgi_params /state/fastcgi_params; mkdir -p /state/elasticsearch/logs /state/elasticsearch/tmp; cp -a /usr/share/java/elasticsearch/config /state/elasticsearch/config; cp -a /usr/share/java/elasticsearch/data /state/elasticsearch/data; chmod -R u+rwX /state/elasticsearch"

def extract(image,target):
    subprocess.run(['apptainer','exec','--cleanenv','--containall','--no-home','--no-mount','bind-paths,hostfs,cwd','--pwd','/','--bind',str(target)+':/state',str(image),'sh','-ec',EXTRACT],check=True,timeout=600)

def prepare(image,state,cache=None,extractor=extract):
    image=Path(image).resolve();state=Path(state);started=time.monotonic()
    if state.is_symlink() or not state.is_dir() or any(state.iterdir()):raise ValueError('Seed destination must be an empty private directory')
    st=image.stat();key=hashlib.sha256(json.dumps([str(image),st.st_size,st.st_mtime_ns,EXTRACT]).encode()).hexdigest()
    hit=False
    if cache is None:extractor(image,state)
    else:
        cache=Path(cache)
        if cache.is_symlink():raise ValueError('Cache root cannot be a symlink')
        if not os.environ.get('SLURM_JOB_ID'):raise RuntimeError('Node-local Slurm cache required')
        cache.resolve().relative_to(Path(os.environ['LAB_ADMIN_NODE_TMPDIR']).resolve())
        if cache.resolve()==state.resolve() or cache.resolve() in state.resolve().parents or state.resolve() in cache.resolve().parents:raise ValueError('Cache and state must be separate')
        cache.mkdir(parents=True,exist_ok=True,mode=0o700);ready=cache/key
        with (cache/'lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            hit=(ready/'ready.json').is_file()
            if not hit:
                with tempfile.TemporaryDirectory(prefix='building-',dir=cache) as tmp:
                    tmp=Path(tmp);data=tmp/'data';data.mkdir();extractor(image,data)
                    (tmp/'ready.json').write_text(json.dumps({'image_key':key,'offline_pristine':True}))
                    # Atomic publish only after extraction succeeds.
                    os.rename(tmp,ready)
            subprocess.run(['cp','-a','--reflink=auto',str(ready/'data')+'/.',str(state)],check=True,timeout=600)
    result={'cache_hit':hit,'seconds':time.monotonic()-started,'image_key':key,'independent_copy':True,'scope':'All image-derived mysql/app/Elasticsearch files; task fixtures applied afterwards'}
    (state/'seed-timing.json').write_text(json.dumps(result,indent=2));return result
